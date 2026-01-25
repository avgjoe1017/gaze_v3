"""Job management endpoints."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.indexer import (
    start_indexing_queued_videos,
    stop_indexing,
    upgrade_to_deep_indexing,
    regenerate_grid_thumbnails,
    pause_indexing,
    resume_indexing,
    is_indexing_paused,
)
from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


JobStatus = Literal[
    "PENDING",
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


class Job(BaseModel):
    """Job model."""

    job_id: str
    video_id: str
    status: JobStatus
    current_stage: str | None = None
    progress: float = 0.0
    message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at_ms: int
    updated_at_ms: int


class JobsResponse(BaseModel):
    """Jobs list response."""

    jobs: list[Job]


@router.get("", response_model=JobsResponse)
async def list_jobs(_token: str = Depends(verify_token)) -> JobsResponse:
    """List all active jobs."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT
                job_id, video_id, status, current_stage, progress,
                message, error_code, error_message, created_at_ms, updated_at_ms
            FROM jobs
            WHERE status NOT IN ('DONE', 'FAILED', 'CANCELLED')
            ORDER BY created_at_ms DESC
            """
        )
        rows = await cursor.fetchall()

        jobs = [
            Job(
                job_id=row["job_id"],
                video_id=row["video_id"],
                status=row["status"],
                current_stage=row["current_stage"],
                progress=row["progress"],
                message=row["message"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                created_at_ms=row["created_at_ms"],
                updated_at_ms=row["updated_at_ms"],
            )
            for row in rows
        ]

        return JobsResponse(jobs=jobs)


# IMPORTANT: This route must be defined BEFORE /{job_id} below
# Otherwise FastAPI will match "/status" as a job_id parameter
@router.get("/status")
async def get_indexing_status(_token: str = Depends(verify_token)) -> dict:
    """Get indexing status (paused state and active job count)."""
    from ..core.indexer import _active_jobs
    
    active_count = len([t for t in _active_jobs.values() if not t.done()])
    queued_count = 0
    async for db in get_db():
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM videos WHERE status = 'QUEUED'"
        )
        row = await cursor.fetchone()
        queued_count = row["count"] if row else 0
    
    return {
        "paused": is_indexing_paused(),
        "active_jobs": active_count,
        "queued_videos": queued_count,
    }


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str, _token: str = Depends(verify_token)) -> Job:
    """Get job details."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT
                job_id, video_id, status, current_stage, progress,
                message, error_code, error_message, created_at_ms, updated_at_ms
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        return Job(
            job_id=row["job_id"],
            video_id=row["video_id"],
            status=row["status"],
            current_stage=row["current_stage"],
            progress=row["progress"],
            message=row["message"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at_ms=row["created_at_ms"],
            updated_at_ms=row["updated_at_ms"],
        )


@router.delete("/{job_id}")
async def cancel_job(job_id: str, _token: str = Depends(verify_token)) -> dict[str, bool]:
    """Cancel a job (including cancelling the running task if active)."""
    video_id = None

    async for db in get_db():
        cursor = await db.execute(
            "SELECT job_id, video_id, status FROM jobs WHERE job_id = ?",
            (job_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        if row["status"] in ("DONE", "FAILED", "CANCELLED"):
            raise HTTPException(status_code=400, detail="Job already completed")

        video_id = row["video_id"]

        # Update job status to cancelled
        await db.execute(
            """
            UPDATE jobs
            SET status = 'CANCELLED', updated_at_ms = ?
            WHERE job_id = ?
            """,
            (int(__import__("time").time() * 1000), job_id),
        )

        # Also update the video status to CANCELLED
        await db.execute(
            """
            UPDATE videos
            SET status = 'CANCELLED', error_code = 'CANCELLED', error_message = 'Cancelled by user'
            WHERE video_id = ?
            """,
            (video_id,),
        )
        await db.execute(
            """
            UPDATE media
            SET status = 'CANCELLED', error_code = 'CANCELLED', error_message = 'Cancelled by user'
            WHERE media_id = ?
            """,
            (video_id,),
        )
        await db.commit()

    # Cancel the actual running task if it exists
    if video_id:
        result = await stop_indexing(video_id)
        if result.get("stopped"):
            logger.info(f"Cancelled running task for job {job_id}, video {video_id}")
        else:
            logger.info(f"Cancelled job {job_id} (no running task found)")
    else:
        logger.info(f"Cancelled job {job_id}")

    return {"success": True}


@router.post("/start")
async def start_indexing(
    limit: int = Query(10, ge=1, le=100),
    _token: str = Depends(verify_token),
) -> dict:
    """Start indexing for queued videos."""
    # Start indexing as a background task using asyncio.create_task
    # This properly handles async functions unlike BackgroundTasks
    asyncio.create_task(start_indexing_queued_videos(limit))
    logger.info(f"Indexing started for up to {limit} queued videos")
    return {"status": "started", "message": f"Indexing queued for up to {limit} videos"}


@router.post("/upgrade-to-deep")
async def upgrade_deep(
    library_id: str | None = Query(None, description="Optional library ID to limit upgrade"),
    _token: str = Depends(verify_token),
) -> dict:
    """
    Upgrade already-indexed videos to deep mode.

    Runs enhanced stages (object detection, face detection, transcription)
    on videos that were previously indexed with 'quick' preset.
    This allows you to start with quick indexing and later upgrade to deep
    without re-indexing everything from scratch.
    """
    result = await upgrade_to_deep_indexing(library_id)
    logger.info(f"Deep upgrade: {result['upgraded']} videos queued, {result['skipped']} skipped")
    return {
        "status": "started",
        "message": f"Deep upgrade started for {result['upgraded']} videos",
        "upgraded": result["upgraded"],
        "skipped": result["skipped"],
    }


@router.post("/regenerate-grid-thumbnails")
async def regenerate_grid_thumbs(
    _token: str = Depends(verify_token),
) -> dict:
    """
    Regenerate grid thumbnails for all existing indexed media.

    Creates small, fast-loading thumbnails (256px, 50% quality) for the media grid.
    Run this once after upgrading to benefit from faster thumbnail loading.
    """
    asyncio.create_task(regenerate_grid_thumbnails())
    logger.info("Grid thumbnail regeneration started")
    return {
        "status": "started",
        "message": "Grid thumbnail regeneration started in background",
    }


@router.post("/pause")
async def pause_indexing_endpoint(_token: str = Depends(verify_token)) -> dict:
    """Pause indexing (stops starting new jobs, but doesn't cancel running ones)."""
    pause_indexing()
    return {"status": "paused", "message": "Indexing paused"}


@router.post("/resume")
async def resume_indexing_endpoint(_token: str = Depends(verify_token)) -> dict:
    """Resume indexing."""
    resume_indexing()
    # Trigger a check to start indexing if there are queued videos
    asyncio.create_task(start_indexing_queued_videos(limit=10))
    return {"status": "resumed", "message": "Indexing resumed"}
