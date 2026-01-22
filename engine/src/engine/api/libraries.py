"""Library management endpoints."""

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.scanner import is_scanning, scan_library_background
from ..core.indexer import stop_indexing
from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..ml.face_detector import get_faces_dir
from ..utils.logging import get_logger
from ..utils.paths import get_faiss_dir, get_thumbnails_dir

logger = get_logger(__name__)

router = APIRouter(prefix="/libraries", tags=["libraries"])


class Library(BaseModel):
    """Library model."""

    library_id: str
    folder_path: str
    name: str | None = None
    recursive: bool = True
    video_count: int = 0
    indexed_count: int = 0
    created_at_ms: int


class LibrariesResponse(BaseModel):
    """List of libraries."""

    libraries: list[Library]


class AddLibraryRequest(BaseModel):
    """Request to add a library."""

    folder_path: str
    name: str | None = None
    recursive: bool = True


class UpdateLibraryRequest(BaseModel):
    """Request to update a library."""

    name: str | None = None


class ScanResponse(BaseModel):
    """Scan response."""

    status: Literal["started", "already_scanning"]


@router.get("", response_model=LibrariesResponse)
async def list_libraries(_token: str = Depends(verify_token)) -> LibrariesResponse:
    """List all libraries."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT
                l.library_id,
                l.folder_path,
                l.name,
                l.recursive,
                l.created_at_ms,
                COUNT(m.media_id) as video_count,
                SUM(CASE WHEN m.status = 'DONE' THEN 1 ELSE 0 END) as indexed_count
            FROM libraries l
            LEFT JOIN media m ON m.library_id = l.library_id
            GROUP BY l.library_id
            ORDER BY l.created_at_ms DESC
            """
        )
        rows = await cursor.fetchall()

        libraries = [
            Library(
                library_id=row["library_id"],
                folder_path=row["folder_path"],
                name=row["name"],
                recursive=bool(row["recursive"]),
                video_count=row["video_count"] or 0,
                indexed_count=row["indexed_count"] or 0,
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        return LibrariesResponse(libraries=libraries)


@router.post("", response_model=Library)
async def add_library(
    request: AddLibraryRequest,
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> Library:
    """Add a new library and start scanning."""
    folder = Path(request.folder_path)

    # Validate path exists
    if not folder.exists():
        raise HTTPException(status_code=400, detail=f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {folder}")

    library_id = str(uuid.uuid4())
    created_at_ms = int(datetime.now().timestamp() * 1000)

    async for db in get_db():
        try:
            await db.execute(
                """
                INSERT INTO libraries (library_id, folder_path, name, recursive, created_at_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (library_id, str(folder), request.name, int(request.recursive), created_at_ms),
            )
            await db.commit()
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(status_code=400, detail="Library path already exists")
            raise

        logger.info(f"Added library {library_id}: {folder}")

        # Start scanning in background
        background_tasks.add_task(
            scan_library_background, library_id, str(folder), request.recursive
        )

        return Library(
            library_id=library_id,
            folder_path=str(folder),
            name=request.name,
            recursive=request.recursive,
            video_count=0,
            indexed_count=0,
            created_at_ms=created_at_ms,
        )


@router.get("/{library_id}", response_model=Library)
async def get_library(library_id: str, _token: str = Depends(verify_token)) -> Library:
    """Get library details."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT
                l.library_id,
                l.folder_path,
                l.name,
                l.recursive,
                l.created_at_ms,
                COUNT(m.media_id) as video_count,
                SUM(CASE WHEN m.status = 'DONE' THEN 1 ELSE 0 END) as indexed_count
            FROM libraries l
            LEFT JOIN media m ON m.library_id = l.library_id
            WHERE l.library_id = ?
            GROUP BY l.library_id
            """,
            (library_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Library not found")

        return Library(
            library_id=row["library_id"],
            folder_path=row["folder_path"],
            name=row["name"],
            recursive=bool(row["recursive"]),
            video_count=row["video_count"] or 0,
            indexed_count=row["indexed_count"] or 0,
            created_at_ms=row["created_at_ms"],
        )


@router.delete("/{library_id}")
async def delete_library(
    library_id: str,
    purge_artifacts: bool = Query(True),
    _token: str = Depends(verify_token),
) -> dict[str, bool]:
    """Delete a library and all its data."""
    video_ids: list[str] = []
    face_crops: list[str] = []

    async for db in get_db():
        cursor = await db.execute(
            "SELECT library_id, folder_path FROM libraries WHERE library_id = ?",
            (library_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Library not found")

        cursor = await db.execute(
            "SELECT video_id FROM videos WHERE library_id = ?",
            (library_id,),
        )
        video_rows = await cursor.fetchall()
        video_ids = [row["video_id"] for row in video_rows]

        if purge_artifacts and video_ids:
            placeholders = ",".join("?" * len(video_ids))
            cursor = await db.execute(
                f"""
                SELECT crop_path FROM faces
                WHERE video_id IN ({placeholders}) AND crop_path IS NOT NULL
                """,
                video_ids,
            )
            face_rows = await cursor.fetchall()
            face_crops = [row["crop_path"] for row in face_rows if row["crop_path"]]

        for video_id in video_ids:
            await stop_indexing(video_id)

        # Delete library (cascade will handle videos, segments, etc.)
        await db.execute("DELETE FROM libraries WHERE library_id = ?", (library_id,))
        await db.commit()

    if purge_artifacts and video_ids:
        thumbnails_dir = get_thumbnails_dir()
        faiss_dir = get_faiss_dir()
        faces_dir = get_faces_dir()

        for video_id in video_ids:
            shutil.rmtree(thumbnails_dir / video_id, ignore_errors=True)
            faiss_path = faiss_dir / f"{video_id}.faiss"
            if faiss_path.exists():
                try:
                    faiss_path.unlink()
                except OSError:
                    pass

        for crop_path in face_crops:
            try:
                crop_file = Path(crop_path)
                if crop_file.is_relative_to(faces_dir):
                    crop_file.unlink(missing_ok=True)
            except Exception:
                pass

    logger.info(f"Deleted library {library_id}")
    return {"success": True}


@router.patch("/{library_id}", response_model=Library)
async def update_library(
    library_id: str,
    request: UpdateLibraryRequest,
    _token: str = Depends(verify_token),
) -> Library:
    """Update library metadata (name, etc.)."""
    async for db in get_db():
        cursor = await db.execute(
            "SELECT library_id FROM libraries WHERE library_id = ?",
            (library_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Library not found")

        await db.execute(
            "UPDATE libraries SET name = ? WHERE library_id = ?",
            (request.name, library_id),
        )
        await db.commit()

        return await get_library(library_id, _token)


@router.post("/{library_id}/scan", response_model=ScanResponse)
async def trigger_scan(
    library_id: str,
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> ScanResponse:
    """Trigger a scan of the library."""
    # Check if already scanning
    if is_scanning(library_id):
        return ScanResponse(status="already_scanning")

    async for db in get_db():
        cursor = await db.execute(
            "SELECT library_id, folder_path, recursive FROM libraries WHERE library_id = ?",
            (library_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Library not found")

        # Start scan in background
        background_tasks.add_task(
            scan_library_background,
            library_id,
            row["folder_path"],
            bool(row["recursive"]),
        )

        logger.info(f"Scan started for library {library_id}")
        return ScanResponse(status="started")
