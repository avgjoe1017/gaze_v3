"""Media endpoints (photos + videos)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.logging import get_logger

logger = get_logger(__name__)

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
    is_live_photo_component: int | None = None
    live_photo_pair_id: str | None = None


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
    include_live_components: bool = Query(False, description="Include LIVE photo video components"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _token: str = Depends(verify_token),
) -> MediaResponse:
    """List media items with optional filters."""
    conditions = []
    params: list = []

    # Filter out LIVE photo components by default
    if not include_live_components:
        conditions.append("m.is_live_photo_component = 0")

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


class GroupedMediaResponse(BaseModel):
    """Media grouped by year-month."""

    groups: dict[str, list[MediaItem]]
    total: int


@router.get("/grouped", response_model=GroupedMediaResponse)
async def get_media_grouped(
    library_id: str | None = Query(None, description="Filter by library"),
    person_id: str | None = Query(None, description="Filter by person in photos"),
    include_live_components: bool = Query(False, description="Include LIVE photo video components"),
    _token: str = Depends(verify_token),
) -> GroupedMediaResponse:
    """Get media items grouped by year-month using creation dates."""
    conditions = []
    params: list = []

    # Filter out LIVE photo components by default (if column exists)
    if not include_live_components:
        conditions.append("(m.is_live_photo_component IS NULL OR m.is_live_photo_component = 0)")

    if library_id:
        conditions.append("m.library_id = ?")
        params.append(library_id)

    if person_id:
        # Join with faces table to filter by person
        conditions.append(
            """EXISTS (
                SELECT 1 FROM faces f
                WHERE f.media_id = m.media_id
                AND f.person_id = ?
            )"""
        )
        params.append(person_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async for db in get_db():
        # Get all media with display dates
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
            ORDER BY
                COALESCE(
                    datetime(m.creation_time),
                    datetime(m.mtime_ms / 1000, 'unixepoch')
                ) DESC
            """,
            params,
        )
        rows = await cursor.fetchall()

        # Group by year-month
        groups: dict[str, list[MediaItem]] = {}
        total = 0

        for row in rows:
            # Extract year-month from creation_time or mtime_ms
            date_str = row["creation_time"]
            year_month = None
            source = None

            if date_str:
                try:
                    # Parse date string - handle multiple formats
                    # ISO format: "2024-01-15T14:30:00" or "2024-01-15"
                    # EXIF converted: "2024:01:15 14:30:00" (should already be converted to ISO)

                    # Replace colons with dashes for first two occurrences (YYYY:MM:DD -> YYYY-MM-DD)
                    normalized = date_str
                    if ":" in date_str[:10]:  # Only check first 10 chars for date part
                        parts = date_str.split(":")
                        if len(parts) >= 3:
                            # Reconstruct: YYYY-MM-DD from YYYY:MM:DD
                            normalized = f"{parts[0]}-{parts[1]}-{parts[2]}"
                            # Add back time if it exists
                            if len(parts) > 3:
                                normalized += ":" + ":".join(parts[3:])

                    # Extract just the date part (before T or space)
                    date_part = normalized.split("T")[0].split(" ")[0].strip()

                    # Must be at least YYYY-MM-DD (10 chars)
                    if len(date_part) >= 10 and date_part[4] == "-" and date_part[7] == "-":
                        year = date_part[0:4]
                        month = date_part[5:7]

                        # Validate year and month
                        if year.isdigit() and month.isdigit():
                            year_int = int(year)
                            month_int = int(month)

                            if 1900 <= year_int <= 2100 and 1 <= month_int <= 12:
                                year_month = f"{year}-{month}"
                                source = "creation_time"
                                media_name = row["filename"] if row["filename"] else row["media_id"]
                                logger.info(f"Media {media_name}: creation_time='{date_str}' -> year_month='{year_month}'")
                            else:
                                media_name = row["filename"] if row["filename"] else row["media_id"]
                                logger.warning(f"Media {media_name}: Date out of range - year={year_int}, month={month_int} from '{date_str}'")
                    else:
                        media_name = row["filename"] if row["filename"] else row["media_id"]
                        logger.warning(f"Media {media_name}: Invalid date format in creation_time: '{date_str}' (date_part='{date_part}')")

                except Exception as e:
                    media_name = row["filename"] if row["filename"] else row["media_id"]
                    logger.warning(f"Media {media_name}: Failed to parse creation_time '{date_str}': {e}")

            if not year_month:
                # Fallback to mtime_ms
                try:
                    mtime_ms = row["mtime_ms"]
                    if mtime_ms and mtime_ms > 0:
                        dt = datetime.fromtimestamp(mtime_ms / 1000)
                        year_month = dt.strftime("%Y-%m")
                        source = "mtime_ms"
                        media_name = row["filename"] if row["filename"] else row["media_id"]
                        logger.info(f"Media {media_name}: Using mtime_ms={mtime_ms} -> year_month='{year_month}' (creation_time was '{date_str}')")
                    else:
                        # Last resort: use current date
                        year_month = datetime.now().strftime("%Y-%m")
                        source = "current"
                        media_name = row["filename"] if row["filename"] else row["media_id"]
                        logger.warning(f"Media {media_name}: No valid date, using current month")
                except Exception as e:
                    # Absolute fallback
                    media_name = row["filename"] if row["filename"] else row["media_id"]
                    logger.error(f"Media {media_name}: Failed to get any date: {e}")
                    year_month = "0000-00"
                    source = "error"

            if year_month not in groups:
                groups[year_month] = []

            media_item = MediaItem(
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
            groups[year_month].append(media_item)
            total += 1

        # Sort groups by key (most recent first)
        sorted_groups = dict(sorted(groups.items(), reverse=True))

        return GroupedMediaResponse(groups=sorted_groups, total=total)

    return GroupedMediaResponse(groups={}, total=0)


@router.get("/{media_id}/live-photo", response_model=MediaItem | None)
async def get_live_photo_component(
    media_id: str,
    _token: str = Depends(verify_token),
) -> MediaItem | None:
    """Get the associated LIVE photo video component for a photo."""
    async for db in get_db():
        # Get the photo to find its pair ID
        cursor = await db.execute(
            "SELECT live_photo_pair_id, fingerprint FROM media WHERE media_id = ?",
            (media_id,),
        )
        photo_row = await cursor.fetchone()

        if not photo_row:
            raise HTTPException(status_code=404, detail="Media not found")

        # Use the pair ID or fingerprint to find the video component
        pair_id = photo_row["live_photo_pair_id"] or photo_row["fingerprint"]

        cursor = await db.execute(
            """
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
            WHERE m.live_photo_pair_id = ?
            AND m.is_live_photo_component = 1
            LIMIT 1
            """,
            (pair_id,),
        )
        video_row = await cursor.fetchone()

        if not video_row:
            return None

        return MediaItem(
            media_id=video_row["media_id"],
            library_id=video_row["library_id"],
            path=video_row["path"],
            filename=video_row["filename"],
            file_ext=video_row["file_ext"],
            media_type=video_row["media_type"],
            file_size=video_row["file_size"],
            mtime_ms=video_row["mtime_ms"],
            fingerprint=video_row["fingerprint"],
            duration_ms=video_row["duration_ms"],
            width=video_row["width"],
            height=video_row["height"],
            creation_time=video_row["creation_time"],
            camera_make=video_row["camera_make"],
            camera_model=video_row["camera_model"],
            gps_lat=video_row["gps_lat"],
            gps_lng=video_row["gps_lng"],
            status=video_row["status"],
            progress=video_row["progress"],
            error_code=video_row["error_code"],
            error_message=video_row["error_message"],
            indexed_at_ms=video_row["indexed_at_ms"],
            created_at_ms=video_row["created_at_ms"],
            thumbnail_path=video_row["thumbnail_path"],
        )

    return None


@router.get("/debug/{filename}")
async def debug_media_by_filename(
    filename: str,
    _token: str = Depends(verify_token),
) -> dict:
    """Debug endpoint to check date metadata for a file by filename."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT media_id, filename, creation_time, mtime_ms, created_at_ms
            FROM media
            WHERE filename LIKE ?
            LIMIT 1
            """,
            (f"%{filename}%",),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Media with filename like '{filename}' not found")

        # Try to parse creation_time
        date_str = row["creation_time"]
        parsed_info = {
            "media_id": row["media_id"],
            "filename": row["filename"],
            "creation_time_raw": date_str,
            "mtime_ms": row["mtime_ms"],
            "created_at_ms": row["created_at_ms"],
            "parsing_attempts": []
        }

        if date_str:
            # Attempt parsing like the grouped endpoint does
            try:
                normalized = date_str
                if ":" in date_str[:10]:
                    parts = date_str.split(":")
                    if len(parts) >= 3:
                        normalized = f"{parts[0]}-{parts[1]}-{parts[2]}"
                        if len(parts) > 3:
                            normalized += ":" + ":".join(parts[3:])

                date_part = normalized.split("T")[0].split(" ")[0].strip()
                parsed_info["parsing_attempts"].append({
                    "step": "normalized_split",
                    "normalized": normalized,
                    "date_part": date_part
                })

                if len(date_part) >= 10 and date_part[4] == "-" and date_part[7] == "-":
                    year = date_part[0:4]
                    month = date_part[5:7]
                    year_month = f"{year}-{month}"

                    year_int = int(year)
                    month_int = int(month)

                    parsed_info["parsing_attempts"].append({
                        "step": "position_extract",
                        "year": year,
                        "month": month,
                        "year_month": year_month,
                        "year_int": year_int,
                        "month_int": month_int,
                        "year_valid": 1900 <= year_int <= 2100,
                        "month_valid": 1 <= month_int <= 12
                    })

                    if 1900 <= year_int <= 2100 and 1 <= month_int <= 12:
                        parsed_info["final_year_month"] = year_month
                        parsed_info["source"] = "creation_time"
                    else:
                        parsed_info["final_year_month"] = None
                        parsed_info["source"] = "validation_failed"
                else:
                    parsed_info["parsing_attempts"].append({
                        "step": "format_check_failed",
                        "reason": f"date_part length={len(date_part)}, char[4]={date_part[4] if len(date_part) > 4 else 'N/A'}, char[7]={date_part[7] if len(date_part) > 7 else 'N/A'}"
                    })
                    parsed_info["final_year_month"] = None
                    parsed_info["source"] = "format_invalid"

            except Exception as e:
                parsed_info["parsing_attempts"].append({
                    "step": "exception",
                    "error": str(e)
                })
                parsed_info["final_year_month"] = None
                parsed_info["source"] = "error"

        # Show what mtime_ms would give
        if row["mtime_ms"] and parsed_info.get("final_year_month") is None:
            try:
                dt = datetime.fromtimestamp(row["mtime_ms"] / 1000)
                year_month_mtime = dt.strftime("%Y-%m")
                parsed_info["mtime_parsed"] = {
                    "year_month": year_month_mtime,
                    "full_date": dt.isoformat()
                }
                if parsed_info.get("final_year_month") is None:
                    parsed_info["final_year_month"] = year_month_mtime
                    parsed_info["source"] = "mtime_ms_fallback"
            except Exception as e:
                parsed_info["mtime_parsed"] = {"error": str(e)}

        return parsed_info

    raise HTTPException(status_code=500, detail="Database error")
