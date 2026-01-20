"""Local asset serving endpoints (thumbnails and videos)."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from ..middleware.auth import verify_token, get_auth_token, is_dev_mode
from ..utils.logging import get_logger
from ..utils.paths import get_thumbnails_dir, get_data_dir

logger = get_logger(__name__)

router = APIRouter(prefix="/assets", tags=["assets"])


def verify_video_token(token: str | None) -> bool:
    """Verify token for video requests (supports query param auth)."""
    # Dev mode bypasses auth
    if is_dev_mode():
        return True

    expected_token = get_auth_token()

    # If no token configured, allow all
    if not expected_token:
        return True

    # Check if provided token matches
    if token and token == expected_token:
        return True

    return False


def _guess_image_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }
    return content_types.get(suffix, "application/octet-stream")


@router.get("/thumbnail")
async def get_thumbnail(
    path: str = Query(..., description="Absolute thumbnail path"),
    _token: str = Depends(verify_token),
) -> FileResponse:
    """Serve a thumbnail image from the thumbnails directory."""
    thumbnails_dir = get_thumbnails_dir().resolve()
    file_path = Path(path).resolve()

    if not file_path.is_relative_to(thumbnails_dir):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(file_path)


@router.get("/face")
async def get_face_crop(
    path: str = Query(..., description="Absolute face crop path"),
    _token: str = Depends(verify_token),
) -> FileResponse:
    """Serve a face crop image from the faces directory."""
    faces_dir = (get_data_dir() / "faces").resolve()
    file_path = Path(path).resolve()

    if not file_path.is_relative_to(faces_dir):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Face crop not found")

    return FileResponse(file_path)


@router.get("/video", response_model=None)
async def get_video(
    request: Request,
    path: str = Query(..., description="Absolute video path"),
    token: str = Query(None, description="Auth token (for video elements that can't send headers)"),
):
    """Serve a video file with support for range requests (seeking)."""
    # Verify token from query param (video elements can't send auth headers)
    if not verify_video_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    file_path = Path(path).resolve()

    logger.info(f"Serving video: {file_path}")

    if not file_path.exists():
        logger.error(f"Video not found: {file_path}")
        raise HTTPException(status_code=404, detail="Video not found")

    # Get file size
    file_size = file_path.stat().st_size

    # Determine content type based on extension
    suffix = file_path.suffix.lower()
    content_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".m4v": "video/x-m4v",
        ".wmv": "video/x-ms-wmv",
        ".flv": "video/x-flv",
    }
    content_type = content_types.get(suffix, "video/mp4")

    # Check for range request (for seeking support)
    range_header = request.headers.get("range")

    if range_header:
        # Parse range header
        try:
            range_spec = range_header.replace("bytes=", "")
            start_str, end_str = range_spec.split("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except (ValueError, AttributeError):
            start = 0
            end = file_size - 1

        # Ensure valid range
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        chunk_size = end - start + 1

        def iter_file():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(8192, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    # No range request - return full file
    return FileResponse(
        file_path,
        media_type=content_type,
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/media", response_model=None)
async def get_media(
    path: str = Query(..., description="Absolute media path"),
    token: str = Query(None, description="Auth token (for media elements that can't send headers)"),
):
    """Serve a media file (photo) via direct path with token auth."""
    if not verify_video_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    file_path = Path(path).resolve()
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media not found")

    return FileResponse(
        file_path,
        media_type=_guess_image_type(file_path),
    )
