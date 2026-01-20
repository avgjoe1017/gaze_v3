"""File scanner for discovering and fingerprinting video files."""

import asyncio
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from ..db.connection import get_db
from ..utils.ffprobe import get_video_metadata
from ..utils.logging import get_logger
from ..ws.handler import emit_scan_progress, emit_scan_complete

logger = get_logger(__name__)

# Supported video extensions
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".3g2", ".ts", ".mts",
}


def compute_fingerprint(path: Path) -> str:
    """
    Compute a content fingerprint for a file.

    Uses file size + hash of first and last 64KB for fast, reliable change detection.
    """
    stat = path.stat()
    file_size = stat.st_size

    if file_size == 0:
        return hashlib.sha256(b"empty").hexdigest()[:16]

    with open(path, "rb") as f:
        # Read first 64KB
        head = f.read(65536)

        # Read last 64KB if file is large enough
        if file_size > 65536:
            f.seek(-65536, 2)
            tail = f.read(65536)
        else:
            tail = b""

    # Combine size and content for fingerprint
    content = f"{file_size}:{head}:{tail}".encode()
    return hashlib.sha256(content).hexdigest()[:16]


async def discover_videos(folder: Path, recursive: bool = True) -> AsyncGenerator[Path, None]:
    """
    Discover video files in a folder.

    Yields paths to video files.
    """
    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"

    for path in folder.glob(pattern):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


async def scan_library(library_id: str, folder_path: str, recursive: bool = True) -> dict:
    """
    Scan a library folder for videos.

    Returns statistics about the scan.
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise ValueError(f"Folder does not exist: {folder}")

    logger.info(f"Starting scan of library {library_id}: {folder}")

    stats = {
        "files_found": 0,
        "files_new": 0,
        "files_changed": 0,
        "files_unchanged": 0,
        "files_deleted": 0,
    }

    # Get existing videos in this library
    existing_videos: dict[str, tuple[str, str]] = {}  # path -> (video_id, fingerprint)

    async for db in get_db():
        cursor = await db.execute(
            "SELECT video_id, path, fingerprint FROM videos WHERE library_id = ?",
            (library_id,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            existing_videos[row["path"]] = (row["video_id"], row["fingerprint"])

    # Track which existing paths we've seen
    seen_paths: set[str] = set()

    # Scan for videos
    async for video_path in discover_videos(folder, recursive):
        stats["files_found"] += 1
        path_str = str(video_path)
        seen_paths.add(path_str)

        try:
            stat = video_path.stat()
            fingerprint = compute_fingerprint(video_path)

            if path_str in existing_videos:
                video_id, old_fingerprint = existing_videos[path_str]

                if fingerprint == old_fingerprint:
                    # Unchanged
                    stats["files_unchanged"] += 1
                else:
                    # Changed - update fingerprint, metadata, and reset status
                    stats["files_changed"] += 1
                    # Re-extract comprehensive metadata for changed files
                    metadata = await get_video_metadata(video_path)

                    async for db in get_db():
                        await db.execute(
                            """
                            UPDATE videos
                            SET fingerprint = ?, mtime_ms = ?, file_size = ?,
                                duration_ms = ?, width = ?, height = ?,
                                fps = ?, video_codec = ?, video_bitrate = ?,
                                audio_codec = ?, audio_channels = ?, audio_sample_rate = ?,
                                container_format = ?, rotation = ?,
                                creation_time = ?, camera_make = ?, camera_model = ?,
                                gps_lat = ?, gps_lng = ?,
                                status = 'QUEUED', progress = 0, last_completed_stage = NULL
                            WHERE video_id = ?
                            """,
                            (
                                fingerprint,
                                int(stat.st_mtime * 1000),
                                stat.st_size,
                                metadata.get("duration_ms"),
                                metadata.get("width"),
                                metadata.get("height"),
                                metadata.get("fps"),
                                metadata.get("video_codec"),
                                metadata.get("video_bitrate"),
                                metadata.get("audio_codec"),
                                metadata.get("audio_channels"),
                                metadata.get("audio_sample_rate"),
                                metadata.get("container_format"),
                                metadata.get("rotation", 0),
                                metadata.get("creation_time"),
                                metadata.get("camera_make"),
                                metadata.get("camera_model"),
                                metadata.get("gps_lat"),
                                metadata.get("gps_lng"),
                                video_id,
                            ),
                        )

                        # Update extra metadata
                        extra_metadata = metadata.get("extra_metadata", {})
                        for key, value in extra_metadata.items():
                            await db.execute(
                                """
                                INSERT OR REPLACE INTO video_metadata (video_id, key, value)
                                VALUES (?, ?, ?)
                                """,
                                (video_id, key, str(value) if value else None),
                            )

                        await db.commit()
                    logger.info(f"Updated changed video: {video_path.name} (codec: {metadata.get('video_codec')})")
            else:
                # New video - extract metadata with ffprobe
                stats["files_new"] += 1
                video_id = str(uuid.uuid4())
                created_at_ms = int(datetime.now().timestamp() * 1000)

                # Extract comprehensive metadata
                metadata = await get_video_metadata(video_path)

                async for db in get_db():
                    await db.execute(
                        """
                        INSERT INTO videos (
                            video_id, library_id, path, filename, file_size,
                            mtime_ms, fingerprint, duration_ms, width, height,
                            fps, video_codec, video_bitrate,
                            audio_codec, audio_channels, audio_sample_rate,
                            container_format, rotation,
                            creation_time, camera_make, camera_model,
                            gps_lat, gps_lng,
                            status, progress, created_at_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 0, ?)
                        """,
                        (
                            video_id,
                            library_id,
                            path_str,
                            video_path.name,
                            stat.st_size,
                            int(stat.st_mtime * 1000),
                            fingerprint,
                            metadata.get("duration_ms"),
                            metadata.get("width"),
                            metadata.get("height"),
                            metadata.get("fps"),
                            metadata.get("video_codec"),
                            metadata.get("video_bitrate"),
                            metadata.get("audio_codec"),
                            metadata.get("audio_channels"),
                            metadata.get("audio_sample_rate"),
                            metadata.get("container_format"),
                            metadata.get("rotation", 0),
                            metadata.get("creation_time"),
                            metadata.get("camera_make"),
                            metadata.get("camera_model"),
                            metadata.get("gps_lat"),
                            metadata.get("gps_lng"),
                            created_at_ms,
                        ),
                    )

                    # Store extra metadata in video_metadata table
                    extra_metadata = metadata.get("extra_metadata", {})
                    for key, value in extra_metadata.items():
                        await db.execute(
                            """
                            INSERT OR REPLACE INTO video_metadata (video_id, key, value)
                            VALUES (?, ?, ?)
                            """,
                            (video_id, key, str(value) if value else None),
                        )

                    await db.commit()
                logger.info(f"Added new video: {video_path.name} (duration: {metadata.get('duration_ms')}ms, codec: {metadata.get('video_codec')})")

        except Exception as e:
            logger.warning(f"Failed to process {video_path}: {e}")

        # Emit progress every 10 files or on new/changed
        if stats["files_found"] % 10 == 0 or stats["files_new"] > 0 or stats["files_changed"] > 0:
            await emit_scan_progress(
                library_id=library_id,
                files_found=stats["files_found"],
                files_new=stats["files_new"],
                files_changed=stats["files_changed"],
                files_deleted=stats["files_deleted"],
            )

    # Check for deleted videos
    for path_str, (video_id, _) in existing_videos.items():
        if path_str not in seen_paths:
            stats["files_deleted"] += 1
            async for db in get_db():
                await db.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
                await db.commit()
            logger.info(f"Removed deleted video: {Path(path_str).name}")

    logger.info(
        f"Scan complete for library {library_id}: "
        f"{stats['files_found']} found, {stats['files_new']} new, "
        f"{stats['files_changed']} changed, {stats['files_deleted']} deleted"
    )

    # Emit completion event
    await emit_scan_complete(library_id, stats)

    return stats


# Track active scans
_active_scans: set[str] = set()


async def scan_library_background(library_id: str, folder_path: str, recursive: bool = True) -> None:
    """Background task to scan a library."""
    global _active_scans

    if library_id in _active_scans:
        logger.warning(f"Scan already in progress for library {library_id}")
        return

    _active_scans.add(library_id)
    try:
        await scan_library(library_id, folder_path, recursive)
    except Exception as e:
        logger.error(f"Scan failed for library {library_id}: {e}")
    finally:
        _active_scans.discard(library_id)


def is_scanning(library_id: str) -> bool:
    """Check if a library is currently being scanned."""
    return library_id in _active_scans
