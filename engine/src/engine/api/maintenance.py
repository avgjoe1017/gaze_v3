"""Maintenance and cleanup endpoints."""

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.indexer import process_stage, stop_indexing
from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..ml.face_detector import get_faces_dir
from ..utils.logging import get_logger
from ..utils.paths import get_faiss_dir, get_thumbnails_dir

logger = get_logger(__name__)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for entry in path.rglob("*") if entry.is_file())


def _wipe_directory(path: Path) -> int:
    """Delete all files in a directory and recreate it."""
    count = _count_files(path)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return count


class WipeDerivedDataResponse(BaseModel):
    status: Literal["ok"]
    cleared_rows: dict[str, int]
    cleared_files: dict[str, int]
    message: str


class FaceDetectRequest(BaseModel):
    library_id: str | None = None
    video_ids: list[str] | None = None
    limit: int = 10
    include_photos: bool = True


class FaceDetectResponse(BaseModel):
    status: Literal["started"]
    started: int
    video_ids: list[str]


@router.post("/wipe-derived", response_model=WipeDerivedDataResponse)
async def wipe_derived_data(_token: str = Depends(verify_token)) -> WipeDerivedDataResponse:
    """Wipe derived indexing artifacts and reset indexing state."""
    logger.info("Wiping derived data: cancelling active jobs")
    await stop_indexing()

    cleared_rows: dict[str, int] = {}
    async for db in get_db():
        # Capture counts before deletion
        for table in ("transcript_segments", "frames", "detections", "faces", "jobs"):
            cursor = await db.execute(f"SELECT COUNT(*) as count FROM {table}")
            row = await cursor.fetchone()
            cleared_rows[table] = row["count"] if row else 0

        # Clear derived tables
        await db.execute("DELETE FROM transcript_segments")
        await db.execute("DELETE FROM transcript_fts")
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM frames")
        await db.execute("DELETE FROM faces")
        await db.execute("DELETE FROM jobs")

        # Reset face metadata on persons
        now_ms = int(datetime.now().timestamp() * 1000)
        await db.execute(
            """
            UPDATE persons
            SET face_count = 0, thumbnail_face_id = NULL, updated_at_ms = ?
            """,
            (now_ms,),
        )

        # Reset indexing state for media and videos
        await db.execute(
            """
            UPDATE videos
            SET status = 'QUEUED',
                last_completed_stage = NULL,
                progress = 0.0,
                error_code = NULL,
                error_message = NULL,
                indexed_at_ms = NULL
            """
        )
        await db.execute(
            """
            UPDATE media
            SET status = 'QUEUED',
                progress = 0.0,
                error_code = NULL,
                error_message = NULL,
                indexed_at_ms = NULL
            """
        )

        await db.commit()

    # Clear derived files on disk
    thumbnails_dir = get_thumbnails_dir()
    faiss_dir = get_faiss_dir()
    faces_dir = get_faces_dir()

    cleared_files = {
        "thumbnails": _wipe_directory(thumbnails_dir),
        "faiss": _wipe_directory(faiss_dir),
        "faces": _wipe_directory(faces_dir),
    }

    logger.info("Derived data wipe complete")
    return WipeDerivedDataResponse(
        status="ok",
        cleared_rows=cleared_rows,
        cleared_files=cleared_files,
        message="Derived data wiped. Re-scan libraries to rebuild indexes.",
    )


async def _is_face_recognition_enabled() -> bool:
    async for db in get_db():
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("face_recognition_enabled",),
        )
        row = await cursor.fetchone()
        if row:
            try:
                return bool(json.loads(row["value"]))
            except Exception:
                return str(row["value"]).lower() == "true"
    return False


async def _run_face_detection(video_id: str, video_path: str, media_type: str) -> None:
    await process_stage(
        video_id,
        Path(video_path),
        "DETECTING_FACES",
        job_id=None,
        media_type=media_type,
    )


@router.post("/wipe-faces", response_model=WipeDerivedDataResponse)
async def wipe_faces_only(_token: str = Depends(verify_token)) -> WipeDerivedDataResponse:
    """Wipe only face recognition data (faces, person assignments, face crops)."""
    logger.info("Wiping face data only")
    
    cleared_rows: dict[str, int] = {}
    async for db in get_db():
        # Capture counts before deletion
        cursor = await db.execute("SELECT COUNT(*) as count FROM faces")
        row = await cursor.fetchone()
        cleared_rows["faces"] = row["count"] if row else 0
        
        cursor = await db.execute("SELECT COUNT(*) as count FROM face_references")
        row = await cursor.fetchone()
        cleared_rows["face_references"] = row["count"] if row else 0
        
        cursor = await db.execute("SELECT COUNT(*) as count FROM face_negatives")
        row = await cursor.fetchone()
        cleared_rows["face_negatives"] = row["count"] if row else 0
        
        cursor = await db.execute("SELECT COUNT(*) as count FROM person_pair_thresholds")
        row = await cursor.fetchone()
        cleared_rows["person_pair_thresholds"] = row["count"] if row else 0

        # Clear face-related tables
        await db.execute("DELETE FROM face_references")
        await db.execute("DELETE FROM face_negatives")
        await db.execute("DELETE FROM person_pair_thresholds")
        await db.execute("DELETE FROM faces")

        # Reset face metadata on persons
        now_ms = int(datetime.now().timestamp() * 1000)
        await db.execute(
            """
            UPDATE persons
            SET face_count = 0, thumbnail_face_id = NULL, updated_at_ms = ?
            """,
            (now_ms,),
        )

        await db.commit()

    # Clear face crop files on disk
    faces_dir = get_faces_dir()
    cleared_files = {
        "faces": _wipe_directory(faces_dir),
    }

    logger.info("Face data wipe complete")
    return WipeDerivedDataResponse(
        status="ok",
        cleared_rows=cleared_rows,
        cleared_files=cleared_files,
        message="Face recognition data wiped. Face detection can be re-run if face recognition is enabled.",
    )


@router.post("/detect-faces", response_model=FaceDetectResponse)
async def detect_faces_pass(
    request: FaceDetectRequest,
    _token: str = Depends(verify_token),
) -> FaceDetectResponse:
    """Run a face-only detection pass on existing frames."""
    if not await _is_face_recognition_enabled():
        raise HTTPException(
            status_code=400,
            detail="Face recognition is disabled. Enable it in Settings to run face detection.",
        )

    limit = max(1, min(int(request.limit or 10), 100))

    async for db in get_db():
        params: list[object] = []
        conditions = ["EXISTS (SELECT 1 FROM frames f WHERE f.video_id = v.video_id)"]

        if request.library_id:
            conditions.append("v.library_id = ?")
            params.append(request.library_id)

        if request.video_ids:
            placeholders = ",".join("?" * len(request.video_ids))
            conditions.append(f"v.video_id IN ({placeholders})")
            params.extend(request.video_ids)

        if not request.include_photos:
            conditions.append("v.media_type = 'video'")

        where_clause = "WHERE " + " AND ".join(conditions)

        cursor = await db.execute(
            f"""
            SELECT v.video_id, v.path, v.media_type
            FROM videos v
            {where_clause}
            ORDER BY v.created_at_ms DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        rows = await cursor.fetchall()

    video_ids = []
    for row in rows:
        video_id = row["video_id"]
        video_ids.append(video_id)
        asyncio.create_task(_run_face_detection(video_id, row["path"], row["media_type"] or "video"))

    logger.info(f"Started face-only detection for {len(video_ids)} items")
    return FaceDetectResponse(status="started", started=len(video_ids), video_ids=video_ids)
