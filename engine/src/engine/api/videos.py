"""Video management endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.indexer import start_indexing_queued_videos
from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])


VideoStatus = Literal[
    "QUEUED",
    "EXTRACTING_AUDIO",
    "TRANSCRIBING",
    "EXTRACTING_FRAMES",
    "EMBEDDING",
    "DETECTING",
    "DETECTING_FACES",
    "DONE",
    "FAILED",
    "CANCELLED",
]


class Video(BaseModel):
    """Video model."""

    video_id: str
    library_id: str
    path: str
    filename: str
    file_size: int | None = None
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    # Technical metadata
    fps: float | None = None
    video_codec: str | None = None
    video_bitrate: int | None = None
    audio_codec: str | None = None
    audio_channels: int | None = None
    audio_sample_rate: int | None = None
    container_format: str | None = None
    rotation: int = 0
    # Source/creation metadata
    creation_time: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    # AI-generated content
    transcript: str | None = None
    # Processing state
    status: VideoStatus
    progress: float = 0.0
    error_code: str | None = None
    error_message: str | None = None
    thumbnail_path: str | None = None
    created_at_ms: int
    indexed_at_ms: int | None = None


class VideoMetadataItem(BaseModel):
    """Key-value metadata item."""

    key: str
    value: str | None


class VideoMetadataResponse(BaseModel):
    """Extra metadata response."""

    video_id: str
    metadata: list[VideoMetadataItem]


class VideosResponse(BaseModel):
    """Videos list response."""

    videos: list[Video]
    total: int


class Frame(BaseModel):
    """Frame thumbnail info."""

    frame_index: int
    timestamp_ms: int
    thumbnail_path: str


class FramesResponse(BaseModel):
    """Frame list response."""

    frames: list[Frame]
    total: int


@router.get("", response_model=VideosResponse)
async def list_videos(
    library_id: str | None = Query(None),
    status: VideoStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _token: str = Depends(verify_token),
) -> VideosResponse:
    """List videos with filtering."""
    async for db in get_db():
        # Build query
        conditions = ["v.media_type = ?"]
        params: list[str | int] = ["video"]

        if library_id:
            conditions.append("v.library_id = ?")
            params.append(library_id)
        if status:
            conditions.append("v.status = ?")
            params.append(status)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM videos v {where_clause}"
        cursor = await db.execute(count_query, params)
        row = await cursor.fetchone()
        total = row[0] if row else 0

        # Get videos with first frame thumbnail
        query = f"""
            SELECT
                v.video_id, v.library_id, v.path, v.filename, v.file_size,
                v.duration_ms, v.width, v.height,
                v.fps, v.video_codec, v.video_bitrate,
                v.audio_codec, v.audio_channels, v.audio_sample_rate,
                v.container_format, v.rotation,
                v.creation_time, v.camera_make, v.camera_model,
                v.gps_lat, v.gps_lng,
                v.transcript,
                v.status, v.progress, v.error_code, v.error_message,
                v.created_at_ms, v.indexed_at_ms,
                (SELECT f.thumbnail_path FROM frames f WHERE f.video_id = v.video_id ORDER BY f.frame_index ASC LIMIT 1) as thumbnail_path
            FROM videos v
            {where_clause}
            ORDER BY v.created_at_ms DESC
            LIMIT ? OFFSET ?
        """
        cursor = await db.execute(query, [*params, limit, offset])
        rows = await cursor.fetchall()

        videos = [
            Video(
                video_id=row["video_id"],
                library_id=row["library_id"],
                path=row["path"],
                filename=row["filename"],
                file_size=row["file_size"],
                duration_ms=row["duration_ms"],
                width=row["width"],
                height=row["height"],
                fps=row["fps"],
                video_codec=row["video_codec"],
                video_bitrate=row["video_bitrate"],
                audio_codec=row["audio_codec"],
                audio_channels=row["audio_channels"],
                audio_sample_rate=row["audio_sample_rate"],
                container_format=row["container_format"],
                rotation=row["rotation"] or 0,
                creation_time=row["creation_time"],
                camera_make=row["camera_make"],
                camera_model=row["camera_model"],
                gps_lat=row["gps_lat"],
                gps_lng=row["gps_lng"],
                transcript=row["transcript"],
                status=row["status"],
                progress=row["progress"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                created_at_ms=row["created_at_ms"],
                indexed_at_ms=row["indexed_at_ms"],
                thumbnail_path=row["thumbnail_path"],
            )
            for row in rows
        ]

        return VideosResponse(videos=videos, total=total)


@router.get("/{video_id}", response_model=Video)
async def get_video(video_id: str, _token: str = Depends(verify_token)) -> Video:
    """Get video details with full metadata."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT
                v.video_id, v.library_id, v.path, v.filename, v.file_size,
                v.duration_ms, v.width, v.height,
                v.fps, v.video_codec, v.video_bitrate,
                v.audio_codec, v.audio_channels, v.audio_sample_rate,
                v.container_format, v.rotation,
                v.creation_time, v.camera_make, v.camera_model,
                v.gps_lat, v.gps_lng,
                v.transcript,
                v.status, v.progress, v.error_code, v.error_message,
                v.created_at_ms, v.indexed_at_ms,
                (SELECT f.thumbnail_path FROM frames f WHERE f.video_id = v.video_id ORDER BY f.frame_index ASC LIMIT 1) as thumbnail_path
            FROM videos v
            WHERE v.video_id = ? AND v.media_type = 'video'
            """,
            (video_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Video not found")

        return Video(
            video_id=row["video_id"],
            library_id=row["library_id"],
            path=row["path"],
            filename=row["filename"],
            file_size=row["file_size"],
            duration_ms=row["duration_ms"],
            width=row["width"],
            height=row["height"],
            fps=row["fps"],
            video_codec=row["video_codec"],
            video_bitrate=row["video_bitrate"],
            audio_codec=row["audio_codec"],
            audio_channels=row["audio_channels"],
            audio_sample_rate=row["audio_sample_rate"],
            container_format=row["container_format"],
            rotation=row["rotation"] or 0,
            creation_time=row["creation_time"],
            camera_make=row["camera_make"],
            camera_model=row["camera_model"],
            gps_lat=row["gps_lat"],
            gps_lng=row["gps_lng"],
            transcript=row["transcript"],
            status=row["status"],
            progress=row["progress"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at_ms=row["created_at_ms"],
            indexed_at_ms=row["indexed_at_ms"],
            thumbnail_path=row["thumbnail_path"],
        )




@router.post("/retry-failed/all")
async def retry_failed_videos(_token: str = Depends(verify_token)) -> dict:
    """Reset all failed/cancelled videos so they can be re-indexed."""
    failed_video_ids: list[str] = []
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT video_id
            FROM videos
            WHERE status IN ('FAILED', 'CANCELLED')
            """
        )
        rows = await cursor.fetchall()
        failed_video_ids = [row["video_id"] for row in rows]
        if not failed_video_ids:
            return {"success": True, "retried": 0, "started": 0}

        placeholders = ",".join("?" * len(failed_video_ids))
        await db.execute(
            f"""
            UPDATE videos
            SET status = 'QUEUED',
                progress = 0.0,
                error_code = NULL,
                error_message = NULL,
                last_completed_stage = NULL
            WHERE video_id IN ({placeholders})
            """,
            failed_video_ids,
        )
        await db.execute(
            f"""
            UPDATE media
            SET status = 'QUEUED',
                progress = 0.0,
                error_code = NULL,
                error_message = NULL
            WHERE media_id IN ({placeholders})
            """,
            failed_video_ids,
        )
        await db.execute(
            f"""
            DELETE FROM jobs
            WHERE video_id IN ({placeholders})
            """,
            failed_video_ids,
        )
        await db.commit()
        break

    started = await start_indexing_queued_videos(limit=10)
    logger.info(f"Requeued {len(failed_video_ids)} failed videos ({started.get('started', 0)} started)")
    return {"success": True, "retried": len(failed_video_ids), "started": started.get("started", 0)}


@router.post("/{video_id}/retry")
async def retry_video(video_id: str, _token: str = Depends(verify_token)) -> dict:
    """Reset a failed video to QUEUED status for re-indexing."""
    async for db in get_db():
        # Check video exists and is in FAILED or CANCELLED state
        cursor = await db.execute(
            "SELECT video_id, status FROM videos WHERE video_id = ?",
            (video_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Video not found")

        if row["status"] not in ("FAILED", "CANCELLED"):
            raise HTTPException(
                status_code=400,
                detail=f"Video is not in a failed state (current: {row['status']})"
            )

        # Reset to QUEUED
        await db.execute(
            """
            UPDATE videos
            SET status = 'QUEUED',
                progress = 0.0,
                error_code = NULL,
                error_message = NULL,
                last_completed_stage = NULL
            WHERE video_id = ?
            """,
            (video_id,),
        )
        await db.commit()

        logger.info(f"Reset video {video_id} to QUEUED for retry")
        return {"success": True, "video_id": video_id, "status": "QUEUED"}


@router.get("/{video_id}/metadata", response_model=VideoMetadataResponse)
async def get_video_metadata(
    video_id: str, _token: str = Depends(verify_token)
) -> VideoMetadataResponse:
    """Get extra metadata for a video (key-value pairs from video_metadata table)."""
    async for db in get_db():
        # Verify video exists
        cursor = await db.execute(
            "SELECT video_id FROM videos WHERE video_id = ?",
            (video_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Video not found")

        # Get metadata
        cursor = await db.execute(
            "SELECT key, value FROM video_metadata WHERE video_id = ? ORDER BY key",
            (video_id,),
        )
        rows = await cursor.fetchall()

        metadata = [
            VideoMetadataItem(key=row["key"], value=row["value"])
            for row in rows
        ]

        return VideoMetadataResponse(video_id=video_id, metadata=metadata)


@router.get("/{video_id}/frames", response_model=FramesResponse)
async def list_frames(
    video_id: str,
    limit: int = Query(15, ge=1, le=50),
    _token: str = Depends(verify_token),
) -> FramesResponse:
    """List thumbnail frames for a video (sampled)."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT frame_index, timestamp_ms, thumbnail_path
            FROM frames
            WHERE video_id = ?
            ORDER BY frame_index ASC
            """,
            (video_id,),
        )
        rows = await cursor.fetchall()

        total = len(rows)
        if total == 0:
            return FramesResponse(frames=[], total=0)

        if total <= limit:
            selected = rows
        else:
            if limit == 1:
                indices = [0]
            else:
                indices = [
                    round(i * (total - 1) / (limit - 1)) for i in range(limit)
                ]
            seen = set()
            selected = []
            for idx in indices:
                if idx in seen:
                    continue
                seen.add(idx)
                selected.append(rows[idx])

        frames = [
            Frame(
                frame_index=row["frame_index"],
                timestamp_ms=row["timestamp_ms"],
                thumbnail_path=row["thumbnail_path"],
            )
            for row in selected
        ]

        return FramesResponse(frames=frames, total=total)
