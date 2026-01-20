"""Model management endpoints."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..core.network import log_outbound_request
from ..utils.logging import get_logger
from ..utils.paths import get_models_dir
from ..ws.handler import emit_model_download_progress, emit_model_download_complete, emit_model_download_error

logger = get_logger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


# Model definitions
MODEL_INFO = {
    "whisper-base": {
        "filename": "whisper-base.pt",
        "size_bytes": 147_000_000,
        "url": "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt",
        "sha256": "ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e",
    },
    "openclip-vit-b-32": {
        "filename": "openclip-vit-b-32.bin",
        "size_bytes": 350_000_000,
        "url": "https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K/resolve/main/open_clip_pytorch_model.bin",
        "sha256": None,  # HuggingFace doesn't provide direct SHA256
    },
    "ssdlite320-mobilenet-v3": {
        "filename": "ssdlite320_mobilenet_v3_large_coco.pth",
        "size_bytes": 13_409_236,
        "url": "https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth",
        "sha256": None,
    },
}

# Track active downloads and their progress
_active_downloads: dict[str, float] = {}
_download_errors: dict[str, str] = {}


async def is_offline_mode() -> bool:
    """Return True if offline mode is enabled in settings."""
    async for db in get_db():
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("offline_mode",),
        )
        row = await cursor.fetchone()
        if row:
            try:
                return bool(json.loads(row["value"]))
            except Exception:
                return str(row["value"]).lower() == "true"
    return False


class ModelInfoResponse(BaseModel):
    """Single model info."""

    name: str
    downloaded: bool
    size_bytes: int
    download_progress: float | None = None
    error: str | None = None


class ModelsResponse(BaseModel):
    """List of models response."""

    models: list[ModelInfoResponse]


class DownloadModelRequest(BaseModel):
    """Request to download a model."""

    model: Literal["whisper-base", "openclip-vit-b-32", "ssdlite320-mobilenet-v3"]


class DownloadModelResponse(BaseModel):
    """Response after starting download."""

    status: Literal["started", "already_downloaded", "downloading", "error"]
    error: str | None = None


async def download_model_task(model_name: str, max_retries: int = 3) -> None:
    """Background task to download a model with retry logic."""
    global _active_downloads, _download_errors

    if model_name not in MODEL_INFO:
        _download_errors[model_name] = f"Unknown model: {model_name}"
        return

    info = MODEL_INFO[model_name]
    models_dir = get_models_dir()
    models_dir.mkdir(parents=True, exist_ok=True)

    model_path = models_dir / info["filename"]
    temp_path = models_dir / f"{info['filename']}.tmp"

    last_error: Exception | None = None

    for attempt in range(max_retries):
        if attempt > 0:
            # Exponential backoff: 2s, 4s, 8s
            delay = 2 ** (attempt + 1)
            logger.info(f"Retry {attempt + 1}/{max_retries} for {model_name} in {delay}s")
            await asyncio.sleep(delay)

        logger.info(f"Starting download of {model_name} from {info['url']} (attempt {attempt + 1})")
        log_outbound_request(
            kind="model_download",
            url=info["url"],
            model=model_name,
            status="started",
            attempt=attempt + 1,
        )

        try:
            # Check for partial download to resume
            start_byte = 0
            if temp_path.exists():
                start_byte = temp_path.stat().st_size
                logger.info(f"Resuming download from byte {start_byte}")

            headers = {}
            if start_byte > 0:
                headers["Range"] = f"bytes={start_byte}-"

            async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
                async with client.stream("GET", info["url"], headers=headers) as response:
                    # Handle partial content (206) or full content (200)
                    if response.status_code == 416:
                        # Range not satisfiable - file already complete or invalid
                        start_byte = 0
                        if temp_path.exists():
                            temp_path.unlink()
                        continue

                    response.raise_for_status()

                    # Determine total size
                    if response.status_code == 206:
                        # Partial content - parse Content-Range
                        content_range = response.headers.get("content-range", "")
                        if "/" in content_range:
                            total_size = int(content_range.split("/")[-1])
                        else:
                            total_size = start_byte + int(response.headers.get("content-length", 0))
                        downloaded = start_byte
                        mode = "ab"  # Append to existing file
                    else:
                        total_size = int(response.headers.get("content-length", 0)) or info["size_bytes"]
                        downloaded = 0
                        mode = "wb"  # Start fresh
                        start_byte = 0

                    # Stream to temp file
                    last_emit_pct = -1
                    with open(temp_path, mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress = downloaded / total_size if total_size > 0 else 0
                            _active_downloads[model_name] = progress

                            # Emit progress every 5% change
                            progress_pct = int(progress * 100)
                            if progress_pct >= last_emit_pct + 5 or progress_pct == 100:
                                last_emit_pct = progress_pct
                                await emit_model_download_progress(
                                    model=model_name,
                                    progress=progress,
                                    bytes_downloaded=downloaded,
                                    bytes_total=total_size,
                                )
                                logger.debug(f"{model_name}: {progress_pct}% downloaded")

            # Verify SHA256 if available
            if info.get("sha256"):
                logger.info(f"Verifying SHA256 for {model_name}")
                sha256 = hashlib.sha256()
                with open(temp_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        sha256.update(chunk)

                if sha256.hexdigest() != info["sha256"]:
                    temp_path.unlink()
                    raise ValueError(f"SHA256 mismatch for {model_name}")

            # Move temp file to final location
            temp_path.rename(model_path)
            logger.info(f"Successfully downloaded {model_name}")

            # Emit completion
            await emit_model_download_complete(model_name)
            log_outbound_request(
                kind="model_download",
                url=info["url"],
                model=model_name,
                status="completed",
                attempt=attempt + 1,
            )

            # Clear any previous error
            _download_errors.pop(model_name, None)
            return  # Success!

        except Exception as e:
            last_error = e
            logger.warning(f"Download attempt {attempt + 1} failed for {model_name}: {e}")
            log_outbound_request(
                kind="model_download",
                url=info["url"],
                model=model_name,
                status="failed",
                attempt=attempt + 1,
                error=str(e),
            )

    # All retries exhausted
    error_msg = f"Failed after {max_retries} attempts: {last_error}"
    logger.error(f"Failed to download {model_name}: {error_msg}")
    _download_errors[model_name] = error_msg
    if temp_path.exists():
        temp_path.unlink()

    # Emit error via WebSocket
    await emit_model_download_error(model_name, str(last_error))

    # Remove from active downloads
    _active_downloads.pop(model_name, None)


@router.get("", response_model=ModelsResponse)
async def list_models(_token: str = Depends(verify_token)) -> ModelsResponse:
    """List all models and their download status."""
    models_dir = get_models_dir()
    models = []

    for name, info in MODEL_INFO.items():
        model_path = models_dir / info["filename"]
        downloaded = model_path.exists()
        progress = _active_downloads.get(name)
        error = _download_errors.get(name)

        models.append(
            ModelInfoResponse(
                name=name,
                downloaded=downloaded,
                size_bytes=info["size_bytes"],
                download_progress=progress,
                error=error,
            )
        )

    return ModelsResponse(models=models)


@router.post("", response_model=DownloadModelResponse)
async def download_model(
    request: DownloadModelRequest,
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> DownloadModelResponse:
    """Start downloading a model."""
    model_name = request.model
    models_dir = get_models_dir()

    if model_name not in MODEL_INFO:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

    info = MODEL_INFO[model_name]
    model_path = models_dir / info["filename"]

    # Clear any previous error
    _download_errors.pop(model_name, None)

    # Check if already downloaded
    if model_path.exists():
        return DownloadModelResponse(status="already_downloaded")

    # Check if already downloading
    if model_name in _active_downloads:
        return DownloadModelResponse(status="downloading")

    if await is_offline_mode():
        return DownloadModelResponse(
            status="error",
            error="Offline mode is enabled. Disable it in settings to download models.",
        )

    # Start download in background
    logger.info(f"Starting background download of {model_name}")
    _active_downloads[model_name] = 0.0
    background_tasks.add_task(download_model_task, model_name)

    return DownloadModelResponse(status="started")


@router.get("/{model_name}/progress")
async def get_download_progress(model_name: str, _token: str = Depends(verify_token)) -> dict:
    """Get download progress for a specific model."""
    if model_name not in MODEL_INFO:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    models_dir = get_models_dir()
    info = MODEL_INFO[model_name]
    model_path = models_dir / info["filename"]

    if model_path.exists():
        return {"status": "complete", "progress": 1.0}

    if model_name in _active_downloads:
        return {"status": "downloading", "progress": _active_downloads[model_name]}

    if model_name in _download_errors:
        return {"status": "error", "error": _download_errors[model_name]}

    return {"status": "pending", "progress": 0.0}
