"""Job management endpoints."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.indexer import start_indexing_queued_videos, stop_indexing
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
            SET status = 'CANCELLED'
            WHERE video_id = ?
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
