"""Media endpoints (photos + videos)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token

router = APIRouter(prefix="/media", tags=["media"])


class MediaItem(BaseModel):
    """Media item model."""

    media_id: str
    library_id: str
    path: str
    filename: str
    file_ext: str | None = None
    media_type: str
    file_size: int
    mtime_ms: int
    fingerprint: str
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    creation_time: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    status: str
    progress: float
    error_code: str | None = None
    error_message: str | None = None
    indexed_at_ms: int | None = None
    created_at_ms: int
    thumbnail_path: str | None = None


class MediaResponse(BaseModel):
    """Media list response."""

    media: list[MediaItem]
    total: int


@router.get("", response_model=MediaResponse)
async def list_media(
    library_id: str | None = Query(None, description="Filter by library"),
    media_type: str | None = Query(None, description="Filter by media type"),
    date_from: str | None = Query(None, description="Filter by mtime date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Filter by mtime date (YYYY-MM-DD)"),
    location_only: bool = Query(False, description="Only items with GPS coordinates"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _token: str = Depends(verify_token),
) -> MediaResponse:
    """List media items with optional filters."""
    conditions = []
    params: list = []

    if library_id:
        conditions.append("m.library_id = ?")
        params.append(library_id)

    if media_type:
        conditions.append("m.media_type = ?")
        params.append(media_type)

    def _parse_date(value: str, end_of_day: bool = False) -> int:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date format") from exc
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        return int(dt.timestamp() * 1000)

    if date_from:
        from_ms = _parse_date(date_from)
        conditions.append("m.mtime_ms >= ?")
        params.append(from_ms)

    if date_to:
        to_ms = _parse_date(date_to, end_of_day=True)
        conditions.append("m.mtime_ms <= ?")
        params.append(to_ms)

    if location_only:
        conditions.append("m.gps_lat IS NOT NULL AND m.gps_lng IS NOT NULL")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async for db in get_db():
        count_cursor = await db.execute(
            f"SELECT COUNT(*) as count FROM media m WHERE {where_clause}",
            params,
        )
        count_row = await count_cursor.fetchone()
        total = count_row["count"] if count_row else 0

        cursor = await db.execute(
            f"""
            SELECT
                m.*,
                (
                    SELECT thumbnail_path
                    FROM frames f
                    WHERE f.video_id = m.media_id
                    ORDER BY f.timestamp_ms
                    LIMIT 1
                ) as thumbnail_path
            FROM media m
            WHERE {where_clause}
            ORDER BY m.created_at_ms DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        rows = await cursor.fetchall()

        media_items = [
            MediaItem(
                media_id=row["media_id"],
                library_id=row["library_id"],
                path=row["path"],
                filename=row["filename"],
                file_ext=row["file_ext"],
                media_type=row["media_type"],
                file_size=row["file_size"],
                mtime_ms=row["mtime_ms"],
                fingerprint=row["fingerprint"],
                duration_ms=row["duration_ms"],
                width=row["width"],
                height=row["height"],
                creation_time=row["creation_time"],
                camera_make=row["camera_make"],
                camera_model=row["camera_model"],
                gps_lat=row["gps_lat"],
                gps_lng=row["gps_lng"],
                status=row["status"],
                progress=row["progress"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                indexed_at_ms=row["indexed_at_ms"],
                created_at_ms=row["created_at_ms"],
                thumbnail_path=row["thumbnail_path"],
            )
            for row in rows
        ]

        return MediaResponse(media=media_items, total=total)

    return MediaResponse(media=[], total=0)
