"""Analytics and statistics endpoint."""

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.logging import get_logger
from ..utils.paths import get_data_dir, get_faiss_dir, get_thumbnails_dir, get_temp_dir

logger = get_logger(__name__)

router = APIRouter(tags=["stats"])


def get_directory_size(path: Path) -> int:
    """Get total size of directory in bytes."""
    total = 0
    try:
        if path.exists() and path.is_dir():
            for entry in path.rglob("*"):
                if entry.is_file():
                    try:
                        total += entry.stat().st_size
                    except (OSError, PermissionError):
                        pass
    except (OSError, PermissionError):
        pass
    return total


class StorageBreakdown(BaseModel):
    """Storage usage breakdown."""

    raw_videos_bytes: int
    indexed_artifacts_bytes: int
    thumbnails_bytes: int
    faiss_shards_bytes: int
    temp_files_bytes: int
    database_bytes: int
    total_bytes: int


class DatabaseStats(BaseModel):
    """Database statistics."""

    total_videos: int
    indexed_videos: int
    queued_videos: int
    processing_videos: int
    failed_videos: int
    total_segments: int
    total_frames: int
    total_detections: int
    total_libraries: int


class IndexingSummary(BaseModel):
    """Indexing status summary."""

    total: int
    indexed: int
    queued: int
    processing: int
    failed: int


class FormatBreakdown(BaseModel):
    """Video format breakdown."""

    container_format: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    count: int
    total_duration_ms: int | None = None


class CodecStats(BaseModel):
    """Codec statistics."""

    containers: list[FormatBreakdown]
    video_codecs: list[FormatBreakdown]
    audio_codecs: list[FormatBreakdown]


class LocationStats(BaseModel):
    """Location/GPS statistics."""

    videos_with_location: int
    total_locations: int


class StatsResponse(BaseModel):
    """Complete statistics response."""

    storage: StorageBreakdown
    database: DatabaseStats
    codecs: CodecStats
    location: LocationStats


@router.get("/stats", response_model=StatsResponse)
async def get_stats(_token: str = Depends(verify_token)) -> StatsResponse:
    """Get comprehensive analytics and statistics."""
    data_dir = get_data_dir()

    # Calculate storage usage
    faiss_dir = get_faiss_dir()
    thumbnails_dir = get_thumbnails_dir()
    temp_dir = get_temp_dir()
    db_path = data_dir / "gaze.db"

    faiss_bytes = get_directory_size(faiss_dir)
    thumbnails_bytes = get_directory_size(thumbnails_dir)
    temp_bytes = get_directory_size(temp_dir)
    database_bytes = db_path.stat().st_size if db_path.exists() else 0

    # Calculate raw video sizes from database
    raw_videos_bytes = 0
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT SUM(file_size) as total_size
            FROM videos
            """
        )
        row = await cursor.fetchone()
        raw_videos_bytes = row["total_size"] or 0

    indexed_artifacts_bytes = faiss_bytes + thumbnails_bytes + temp_bytes + database_bytes
    total_bytes = raw_videos_bytes + indexed_artifacts_bytes

    storage = StorageBreakdown(
        raw_videos_bytes=raw_videos_bytes,
        indexed_artifacts_bytes=indexed_artifacts_bytes,
        thumbnails_bytes=thumbnails_bytes,
        faiss_shards_bytes=faiss_bytes,
        temp_files_bytes=temp_bytes,
        database_bytes=database_bytes,
        total_bytes=total_bytes,
    )

    # Database statistics
    async for db in get_db():
        # Video counts by status
        cursor = await db.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'DONE' THEN 1 ELSE 0 END) as indexed,
                SUM(CASE WHEN status = 'QUEUED' THEN 1 ELSE 0 END) as queued,
                SUM(CASE WHEN status IN ('EXTRACTING_AUDIO', 'TRANSCRIBING', 'EXTRACTING_FRAMES', 'EMBEDDING', 'DETECTING') THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
            FROM videos
            """
        )
        video_row = await cursor.fetchone()

        # Segment count
        cursor = await db.execute("SELECT COUNT(*) as count FROM transcript_segments")
        segment_row = await cursor.fetchone()

        # Frame count
        cursor = await db.execute("SELECT COUNT(*) as count FROM frames")
        frame_row = await cursor.fetchone()

        # Detection count
        cursor = await db.execute("SELECT COUNT(*) as count FROM detections")
        detection_row = await cursor.fetchone()

        # Library count
        cursor = await db.execute("SELECT COUNT(*) as count FROM libraries")
        library_row = await cursor.fetchone()

        database = DatabaseStats(
            total_videos=video_row["total"] or 0,
            indexed_videos=video_row["indexed"] or 0,
            queued_videos=video_row["queued"] or 0,
            processing_videos=video_row["processing"] or 0,
            failed_videos=video_row["failed"] or 0,
            total_segments=segment_row["count"] or 0,
            total_frames=frame_row["count"] or 0,
            total_detections=detection_row["count"] or 0,
            total_libraries=library_row["count"] or 0,
        )

    # Format breakdown
    async for db in get_db():
        # Container formats
        cursor = await db.execute(
            """
            SELECT
                container_format,
                COUNT(*) as count,
                SUM(duration_ms) as total_duration
            FROM videos
            WHERE container_format IS NOT NULL
            GROUP BY container_format
            ORDER BY count DESC
            """
        )
        container_rows = await cursor.fetchall()

        # Video codecs
        cursor = await db.execute(
            """
            SELECT
                video_codec,
                COUNT(*) as count,
                SUM(duration_ms) as total_duration
            FROM videos
            WHERE video_codec IS NOT NULL
            GROUP BY video_codec
            ORDER BY count DESC
            """
        )
        video_codec_rows = await cursor.fetchall()

        # Audio codecs
        cursor = await db.execute(
            """
            SELECT
                audio_codec,
                COUNT(*) as count,
                SUM(duration_ms) as total_duration
            FROM videos
            WHERE audio_codec IS NOT NULL
            GROUP BY audio_codec
            ORDER BY count DESC
            """
        )
        audio_codec_rows = await cursor.fetchall()

        codecs = CodecStats(
            containers=[
                FormatBreakdown(
                    container_format=row["container_format"],
                    video_codec=None,
                    count=row["count"],
                    total_duration_ms=row["total_duration"],
                )
                for row in container_rows
            ],
            video_codecs=[
                FormatBreakdown(
                    container_format=None,
                    video_codec=row["video_codec"],
                    count=row["count"],
                    total_duration_ms=row["total_duration"],
                )
                for row in video_codec_rows
            ],
            audio_codecs=[
                FormatBreakdown(
                    audio_codec=row["audio_codec"],
                    count=row["count"],
                    total_duration_ms=row["total_duration"],
                )
                for row in audio_codec_rows
            ],
        )

    # Location statistics
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT
                COUNT(DISTINCT video_id) as videos_with_location,
                COUNT(*) as total_locations
            FROM videos
            WHERE gps_lat IS NOT NULL AND gps_lng IS NOT NULL
            """
        )
        location_row = await cursor.fetchone()

        location = LocationStats(
            videos_with_location=location_row["videos_with_location"] or 0,
            total_locations=location_row["total_locations"] or 0,
        )

    return StatsResponse(
        storage=storage,
        database=database,
        codecs=codecs,
        location=location,
    )


@router.get("/stats/indexing", response_model=IndexingSummary)
async def get_indexing_summary(
    library_id: str | None = None,
    _token: str = Depends(verify_token),
) -> IndexingSummary:
    """Get indexing status summary for videos (optionally filtered by library)."""
    async for db in get_db():
        conditions = ["media_type = 'video'"]
        params: list[str] = []
        if library_id:
            conditions.append("library_id = ?")
            params.append(library_id)

        where_clause = "WHERE " + " AND ".join(conditions)
        cursor = await db.execute(
            f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'DONE' THEN 1 ELSE 0 END) as indexed,
                SUM(CASE WHEN status = 'QUEUED' THEN 1 ELSE 0 END) as queued,
                SUM(CASE WHEN status IN (
                    'EXTRACTING_AUDIO',
                    'TRANSCRIBING',
                    'EXTRACTING_FRAMES',
                    'EMBEDDING',
                    'DETECTING',
                    'DETECTING_FACES'
                ) THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
            FROM videos
            {where_clause}
            """,
            params,
        )
        row = await cursor.fetchone()

        return IndexingSummary(
            total=row["total"] or 0,
            indexed=row["indexed"] or 0,
            queued=row["queued"] or 0,
            processing=row["processing"] or 0,
            failed=row["failed"] or 0,
        )
