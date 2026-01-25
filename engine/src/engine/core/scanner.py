"""File scanner for discovering and fingerprinting media files."""

import asyncio
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from ..db.connection import get_db
from ..utils.ffprobe import get_video_metadata
from ..utils.image_metadata import get_image_metadata
from ..utils.logging import get_logger
from ..ws.handler import emit_scan_progress, emit_scan_complete

logger = get_logger(__name__)

# Supported video extensions
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".3g2", ".ts", ".mts",
}

# Supported photo extensions
PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp",
    ".bmp", ".tiff", ".tif", ".gif",
}

MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | PHOTO_EXTENSIONS

IN_PROGRESS_STATUSES = (
    "EXTRACTING_AUDIO",
    "TRANSCRIBING",
    "EXTRACTING_FRAMES",
    "EMBEDDING",
    "DETECTING",
    "DETECTING_FACES",
)


def detect_live_photo_pairs(files: list[Path]) -> dict[Path, Path]:
    """Detect iPhone LIVE photo pairs (.heic/.jpg + .mov).

    Returns a mapping of photo_path -> video_path for detected pairs.
    """
    pairs: dict[Path, Path] = {}

    # Group files by stem (filename without extension)
    photo_files = {f for f in files if f.suffix.lower() in {".heic", ".heif", ".jpg", ".jpeg"}}
    video_files = {f for f in files if f.suffix.lower() == ".mov"}

    for photo in photo_files:
        # Look for matching .mov with same stem
        matching_mov = photo.with_suffix(".mov")
        if matching_mov not in video_files:
            matching_mov = photo.with_suffix(".MOV")

        if matching_mov in video_files:
            # LIVE photos are very short videos (typically 1.5-3 seconds)
            # We'll mark them as pairs and verify duration during indexing
            pairs[photo] = matching_mov

    logger.info(f"Detected {len(pairs)} potential LIVE photo pairs")
    return pairs


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


async def discover_media(folder: Path, recursive: bool = True) -> AsyncGenerator[Path, None]:
    """
    Discover media files in a folder.

    Yields paths to media files.
    """
    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"

    for path in folder.glob(pattern):
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
            yield path


async def scan_library(library_id: str, folder_path: str, recursive: bool = True) -> dict:
    """
    Scan a library folder for media.

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

    # Get existing media in this library
    existing_media: dict[str, tuple[str, str, str]] = {}  # path -> (media_id, media_type, fingerprint)
    existing_videos: dict[str, tuple[str, str, str]] = {}  # path -> (video_id, fingerprint, media_type)

    async for db in get_db():
        cursor = await db.execute(
            "SELECT media_id, path, media_type, fingerprint FROM media WHERE library_id = ?",
            (library_id,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            existing_media[row["path"]] = (row["media_id"], row["media_type"], row["fingerprint"])

        cursor = await db.execute(
            "SELECT video_id, path, fingerprint, media_type FROM videos WHERE library_id = ?",
            (library_id,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            existing_videos[row["path"]] = (
                row["video_id"],
                row["fingerprint"],
                row["media_type"] or "video",
            )

    # Track which existing paths we've seen
    seen_paths: set[str] = set()

    # Scan for videos
    async for media_path in discover_media(folder, recursive):
        stats["files_found"] += 1
        path_str = str(media_path)
        seen_paths.add(path_str)

        try:
            stat = media_path.stat()
            fingerprint = compute_fingerprint(media_path)
            media_type = "video" if media_path.suffix.lower() in VIDEO_EXTENSIONS else "photo"

            if media_type == "video":
                metadata = await get_video_metadata(media_path)
            else:
                metadata = await get_image_metadata(media_path)

            # Check if this file is part of a LIVE photo pair
            is_live_component = False
            live_pair_id = None

            if media_type == "photo" and media_path.suffix.lower() in {".heic", ".heif", ".jpg", ".jpeg"}:
                # Check if there's a matching .mov file
                matching_mov = media_path.with_suffix(".mov")
                if not matching_mov.exists():
                    matching_mov = media_path.with_suffix(".MOV")

                if matching_mov.exists():
                    # This photo has a paired video - mark the video as LIVE component
                    live_pair_id = fingerprint  # Use photo's fingerprint as pair ID
            elif media_type == "video" and media_path.suffix.lower() == ".mov":
                # Check if there's a matching photo file
                for ext in [".heic", ".HEIC", ".heif", ".HEIF", ".jpg", ".JPG", ".jpeg", ".JPEG"]:
                    matching_photo = media_path.with_suffix(ext)
                    if matching_photo.exists():
                        # Verify it's a short video (LIVE photos are < 5 seconds)
                        duration_ms = metadata.get("duration_ms") if metadata else None
                        if duration_ms and duration_ms < 5000:  # Less than 5 seconds
                            is_live_component = True
                            # Use the photo's fingerprint as pair ID
                            live_pair_id = compute_fingerprint(matching_photo)
                        break

            if path_str in existing_media:
                media_id, old_media_type, old_fingerprint = existing_media[path_str]

                if fingerprint == old_fingerprint and media_type == old_media_type:
                    stats["files_unchanged"] += 1
                else:
                    stats["files_changed"] += 1

                    async for db in get_db():
                        await db.execute(
                            """
                            UPDATE media
                            SET fingerprint = ?, mtime_ms = ?, file_size = ?, media_type = ?, file_ext = ?,
                                duration_ms = ?, width = ?, height = ?,
                                creation_time = ?, camera_make = ?, camera_model = ?,
                                gps_lat = ?, gps_lng = ?,
                                is_live_photo_component = ?, live_photo_pair_id = ?,
                                status = 'QUEUED', progress = 0, error_code = NULL, error_message = NULL
                            WHERE media_id = ?
                            """,
                            (
                                fingerprint,
                                int(stat.st_mtime * 1000),
                                stat.st_size,
                                media_type,
                                media_path.suffix.lower(),
                                metadata.get("duration_ms") if metadata else None,
                                metadata.get("width") if metadata else None,
                                metadata.get("height") if metadata else None,
                                metadata.get("creation_time") if metadata else None,
                                metadata.get("camera_make") if metadata else None,
                                metadata.get("camera_model") if metadata else None,
                                metadata.get("gps_lat") if metadata else None,
                                metadata.get("gps_lng") if metadata else None,
                                1 if is_live_component else 0,
                                live_pair_id,
                                media_id,
                            ),
                        )

                        await db.execute("DELETE FROM media_metadata WHERE media_id = ?", (media_id,))
                        if media_type == "photo":
                            extra_metadata = metadata.get("extra_metadata", {}) if metadata else {}
                            for key, value in extra_metadata.items():
                                await db.execute(
                                    """
                                    INSERT OR REPLACE INTO media_metadata (media_id, key, value)
                                    VALUES (?, ?, ?)
                                    """,
                                    (media_id, key, str(value)),
                                )
                        await db.commit()

                    async for db in get_db():
                        if path_str in existing_videos:
                            if media_type == "video":
                                await db.execute(
                                    """
                                    UPDATE videos
                                    SET media_type = ?, fingerprint = ?, mtime_ms = ?, file_size = ?,
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
                                        media_type,
                                        fingerprint,
                                        int(stat.st_mtime * 1000),
                                        stat.st_size,
                                        metadata.get("duration_ms") if metadata else None,
                                        metadata.get("width") if metadata else None,
                                        metadata.get("height") if metadata else None,
                                        metadata.get("fps") if metadata else None,
                                        metadata.get("video_codec") if metadata else None,
                                        metadata.get("video_bitrate") if metadata else None,
                                        metadata.get("audio_codec") if metadata else None,
                                        metadata.get("audio_channels") if metadata else None,
                                        metadata.get("audio_sample_rate") if metadata else None,
                                        metadata.get("container_format") if metadata else None,
                                        metadata.get("rotation", 0) if metadata else 0,
                                        metadata.get("creation_time") if metadata else None,
                                        metadata.get("camera_make") if metadata else None,
                                        metadata.get("camera_model") if metadata else None,
                                        metadata.get("gps_lat") if metadata else None,
                                        metadata.get("gps_lng") if metadata else None,
                                        media_id,
                                    ),
                                )
                            else:
                                await db.execute(
                                    """
                                    UPDATE videos
                                    SET media_type = ?, fingerprint = ?, mtime_ms = ?, file_size = ?,
                                        duration_ms = NULL, width = ?, height = ?,
                                        fps = NULL, video_codec = NULL, video_bitrate = NULL,
                                        audio_codec = NULL, audio_channels = NULL, audio_sample_rate = NULL,
                                        container_format = NULL, rotation = 0,
                                        creation_time = ?, camera_make = ?, camera_model = ?,
                                        gps_lat = ?, gps_lng = ?,
                                        status = 'QUEUED', progress = 0, last_completed_stage = NULL
                                    WHERE video_id = ?
                                    """,
                                    (
                                        media_type,
                                        fingerprint,
                                        int(stat.st_mtime * 1000),
                                        stat.st_size,
                                        metadata.get("width") if metadata else None,
                                        metadata.get("height") if metadata else None,
                                        metadata.get("creation_time") if metadata else None,
                                        metadata.get("camera_make") if metadata else None,
                                        metadata.get("camera_model") if metadata else None,
                                        metadata.get("gps_lat") if metadata else None,
                                        metadata.get("gps_lng") if metadata else None,
                                        media_id,
                                    ),
                                )
                        else:
                            created_at_ms = int(datetime.now().timestamp() * 1000)
                            if media_type == "video":
                                await db.execute(
                                    """
                                    INSERT INTO videos (
                                        video_id, library_id, path, filename, media_type, file_size,
                                        mtime_ms, fingerprint, duration_ms, width, height,
                                        fps, video_codec, video_bitrate,
                                        audio_codec, audio_channels, audio_sample_rate,
                                        container_format, rotation,
                                        creation_time, camera_make, camera_model,
                                        gps_lat, gps_lng,
                                        status, progress, created_at_ms
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 0, ?)
                                    """,
                                    (
                                        media_id,
                                        library_id,
                                        path_str,
                                        media_path.name,
                                        media_type,
                                        stat.st_size,
                                        int(stat.st_mtime * 1000),
                                        fingerprint,
                                        metadata.get("duration_ms") if metadata else None,
                                        metadata.get("width") if metadata else None,
                                        metadata.get("height") if metadata else None,
                                        metadata.get("fps") if metadata else None,
                                        metadata.get("video_codec") if metadata else None,
                                        metadata.get("video_bitrate") if metadata else None,
                                        metadata.get("audio_codec") if metadata else None,
                                        metadata.get("audio_channels") if metadata else None,
                                        metadata.get("audio_sample_rate") if metadata else None,
                                        metadata.get("container_format") if metadata else None,
                                        metadata.get("rotation", 0) if metadata else 0,
                                        metadata.get("creation_time") if metadata else None,
                                        metadata.get("camera_make") if metadata else None,
                                        metadata.get("camera_model") if metadata else None,
                                        metadata.get("gps_lat") if metadata else None,
                                        metadata.get("gps_lng") if metadata else None,
                                        created_at_ms,
                                    ),
                                )
                            else:
                                await db.execute(
                                    """
                                    INSERT INTO videos (
                                        video_id, library_id, path, filename, media_type, file_size,
                                        mtime_ms, fingerprint, duration_ms, width, height,
                                        fps, video_codec, video_bitrate,
                                        audio_codec, audio_channels, audio_sample_rate,
                                        container_format, rotation,
                                        creation_time, camera_make, camera_model,
                                        gps_lat, gps_lng,
                                        status, progress, created_at_ms
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?, ?, ?, ?, 'QUEUED', 0, ?)
                                    """,
                                    (
                                        media_id,
                                        library_id,
                                        path_str,
                                        media_path.name,
                                        media_type,
                                        stat.st_size,
                                        int(stat.st_mtime * 1000),
                                        fingerprint,
                                        metadata.get("width") if metadata else None,
                                        metadata.get("height") if metadata else None,
                                        metadata.get("creation_time") if metadata else None,
                                        metadata.get("camera_make") if metadata else None,
                                        metadata.get("camera_model") if metadata else None,
                                        metadata.get("gps_lat") if metadata else None,
                                        metadata.get("gps_lng") if metadata else None,
                                        created_at_ms,
                                    ),
                                )

                        await db.execute("DELETE FROM video_metadata WHERE video_id = ?", (media_id,))
                        await db.commit()

                    if media_type == "video":
                        extra_metadata = metadata.get("extra_metadata", {}) if metadata else {}
                        async for db in get_db():
                            for key, value in extra_metadata.items():
                                await db.execute(
                                    """
                                    INSERT OR REPLACE INTO video_metadata (video_id, key, value)
                                    VALUES (?, ?, ?)
                                    """,
                                    (media_id, key, str(value) if value else None),
                                )
                            await db.commit()
            else:
                stats["files_new"] += 1
                media_id = str(uuid.uuid4())
                created_at_ms = int(datetime.now().timestamp() * 1000)

                async for db in get_db():
                    await db.execute(
                        """
                        INSERT INTO media (
                            media_id, library_id, path, filename, file_ext, media_type,
                            file_size, mtime_ms, fingerprint, duration_ms, width, height,
                            creation_time, camera_make, camera_model, gps_lat, gps_lng,
                            is_live_photo_component, live_photo_pair_id,
                            status, progress, indexed_at_ms, created_at_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 0, NULL, ?)
                        """,
                        (
                            media_id,
                            library_id,
                            path_str,
                            media_path.name,
                            media_path.suffix.lower(),
                            media_type,
                            stat.st_size,
                            int(stat.st_mtime * 1000),
                            fingerprint,
                            metadata.get("duration_ms") if metadata else None,
                            metadata.get("width") if metadata else None,
                            metadata.get("height") if metadata else None,
                            metadata.get("creation_time") if metadata else None,
                            metadata.get("camera_make") if metadata else None,
                            metadata.get("camera_model") if metadata else None,
                            metadata.get("gps_lat") if metadata else None,
                            metadata.get("gps_lng") if metadata else None,
                            1 if is_live_component else 0,
                            live_pair_id,
                            created_at_ms,
                        ),
                    )
                    if media_type == "photo":
                        extra_metadata = metadata.get("extra_metadata", {}) if metadata else {}
                        for key, value in extra_metadata.items():
                            await db.execute(
                                """
                                INSERT OR REPLACE INTO media_metadata (media_id, key, value)
                                VALUES (?, ?, ?)
                                """,
                                (media_id, key, str(value)),
                            )
                    await db.commit()

                async for db in get_db():
                    if media_type == "video":
                        await db.execute(
                            """
                            INSERT INTO videos (
                                video_id, library_id, path, filename, media_type, file_size,
                                mtime_ms, fingerprint, duration_ms, width, height,
                                fps, video_codec, video_bitrate,
                                audio_codec, audio_channels, audio_sample_rate,
                                container_format, rotation,
                                creation_time, camera_make, camera_model,
                                gps_lat, gps_lng,
                                status, progress, created_at_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 0, ?)
                            """,
                            (
                                media_id,
                                library_id,
                                path_str,
                                media_path.name,
                                media_type,
                                stat.st_size,
                                int(stat.st_mtime * 1000),
                                fingerprint,
                                metadata.get("duration_ms") if metadata else None,
                                metadata.get("width") if metadata else None,
                                metadata.get("height") if metadata else None,
                                metadata.get("fps") if metadata else None,
                                metadata.get("video_codec") if metadata else None,
                                metadata.get("video_bitrate") if metadata else None,
                                metadata.get("audio_codec") if metadata else None,
                                metadata.get("audio_channels") if metadata else None,
                                metadata.get("audio_sample_rate") if metadata else None,
                                metadata.get("container_format") if metadata else None,
                                metadata.get("rotation", 0) if metadata else 0,
                                metadata.get("creation_time") if metadata else None,
                                metadata.get("camera_make") if metadata else None,
                                metadata.get("camera_model") if metadata else None,
                                metadata.get("gps_lat") if metadata else None,
                                metadata.get("gps_lng") if metadata else None,
                                created_at_ms,
                            ),
                        )
                    else:
                        await db.execute(
                            """
                            INSERT INTO videos (
                                video_id, library_id, path, filename, media_type, file_size,
                                mtime_ms, fingerprint, duration_ms, width, height,
                                fps, video_codec, video_bitrate,
                                audio_codec, audio_channels, audio_sample_rate,
                                container_format, rotation,
                                creation_time, camera_make, camera_model,
                                gps_lat, gps_lng,
                                status, progress, created_at_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?, ?, ?, ?, 'QUEUED', 0, ?)
                            """,
                            (
                                media_id,
                                library_id,
                                path_str,
                                media_path.name,
                                media_type,
                                stat.st_size,
                                int(stat.st_mtime * 1000),
                                fingerprint,
                                metadata.get("width") if metadata else None,
                                metadata.get("height") if metadata else None,
                                metadata.get("creation_time") if metadata else None,
                                metadata.get("camera_make") if metadata else None,
                                metadata.get("camera_model") if metadata else None,
                                metadata.get("gps_lat") if metadata else None,
                                metadata.get("gps_lng") if metadata else None,
                                created_at_ms,
                            ),
                        )
                    await db.commit()

                if media_type == "video":
                    extra_metadata = metadata.get("extra_metadata", {}) if metadata else {}
                    async for db in get_db():
                        for key, value in extra_metadata.items():
                            await db.execute(
                                """
                                INSERT OR REPLACE INTO video_metadata (video_id, key, value)
                                VALUES (?, ?, ?)
                                """,
                                (media_id, key, str(value) if value else None),
                            )
                        await db.commit()

                if media_type == "video":
                    logger.info(
                        f"Added new video: {media_path.name} (duration: {metadata.get('duration_ms')}ms)"
                    )
                else:
                    logger.info(f"Added new photo: {media_path.name}")
        except Exception as e:
            logger.warning(f"Failed to process {media_path}: {e}")

        # Emit progress every 10 files or on new/changed
        if stats["files_found"] % 10 == 0 or stats["files_new"] > 0 or stats["files_changed"] > 0:
            await emit_scan_progress(
                library_id=library_id,
                files_found=stats["files_found"],
                files_new=stats["files_new"],
                files_changed=stats["files_changed"],
                files_deleted=stats["files_deleted"],
            )

    # Check for deleted media
    for path_str, (media_id, media_type, _) in existing_media.items():
        if path_str not in seen_paths:
            stats["files_deleted"] += 1
            async for db in get_db():
                await db.execute("DELETE FROM media WHERE media_id = ?", (media_id,))
                await db.execute("DELETE FROM videos WHERE video_id = ?", (media_id,))
                await db.commit()
            logger.info(f"Removed deleted {media_type}: {Path(path_str).name}")

    logger.info(
        f"Scan complete for library {library_id}: "
        f"{stats['files_found']} found, {stats['files_new']} new, "
        f"{stats['files_changed']} changed, {stats['files_deleted']} deleted"
    )

    # Resync behavior: ensure all unindexed items are queued for processing
    async for db in get_db():
        placeholders = ",".join("?" * len(IN_PROGRESS_STATUSES))
        # Videos
        cursor = await db.execute(
            f"""
            SELECT COUNT(*) as count
            FROM videos
            WHERE library_id = ?
              AND status != 'DONE'
              AND status NOT IN ({placeholders})
            """,
            (library_id, *IN_PROGRESS_STATUSES),
        )
        row = await cursor.fetchone()
        to_queue_videos = row["count"] if row else 0

        await db.execute(
            f"""
            UPDATE videos
            SET status = 'QUEUED',
                progress = 0,
                error_code = NULL,
                error_message = NULL,
                last_completed_stage = NULL
            WHERE library_id = ?
              AND status != 'DONE'
              AND status NOT IN ({placeholders})
            """,
            (library_id, *IN_PROGRESS_STATUSES),
        )

        # Media
        cursor = await db.execute(
            f"""
            SELECT COUNT(*) as count
            FROM media
            WHERE library_id = ?
              AND status != 'DONE'
              AND status NOT IN ({placeholders})
            """,
            (library_id, *IN_PROGRESS_STATUSES),
        )
        row = await cursor.fetchone()
        to_queue_media = row["count"] if row else 0

        await db.execute(
            f"""
            UPDATE media
            SET status = 'QUEUED',
                progress = 0,
                error_code = NULL,
                error_message = NULL
            WHERE library_id = ?
              AND status != 'DONE'
              AND status NOT IN ({placeholders})
            """,
            (library_id, *IN_PROGRESS_STATUSES),
        )

        await db.commit()

    if to_queue_videos or to_queue_media:
        logger.info(
            f"Resync queued {to_queue_videos} videos and {to_queue_media} media items for indexing"
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
