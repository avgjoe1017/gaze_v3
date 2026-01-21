"""Maintenance and cleanup endpoints."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.indexer import stop_indexing
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
