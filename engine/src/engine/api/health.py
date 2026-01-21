"""Health check endpoint."""

import asyncio
import os
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..core.lifecycle import get_ffmpeg_status, get_gpu_status
from ..middleware.auth import verify_token
from ..utils.logging import get_logger
from ..utils.paths import get_models_dir

logger = get_logger(__name__)

router = APIRouter(tags=["health"])

# Track start time
_start_time = datetime.now()

# Required models
REQUIRED_MODELS = ["whisper-base", "openclip-vit-b-32", "ssdlite320-mobilenet-v3"]


class DependencyStatus(BaseModel):
    """External dependency status."""

    ffmpeg_available: bool
    ffmpeg_version: str | None
    ffprobe_available: bool
    ffprobe_version: str | None
    gpu_available: bool
    gpu_name: str | None
    gpu_memory_mb: int | None


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["starting", "ready", "error"]
    models_ready: bool
    missing_models: list[str]
    dependencies: DependencyStatus
    engine_uuid: str
    uptime_ms: int


def check_models_downloaded() -> tuple[bool, list[str]]:
    """Check which models are downloaded."""
    models_dir = get_models_dir()
    missing = []

    model_files = {
        "whisper-base": "whisper-base.pt",
        "openclip-vit-b-32": "openclip-vit-b-32.bin",
        "ssdlite320-mobilenet-v3": "ssdlite320_mobilenet_v3_large_coco.pth",
    }

    for model_name, filename in model_files.items():
        if not (models_dir / filename).exists():
            missing.append(model_name)

    return len(missing) == 0, missing


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Get engine health status."""
    engine_uuid = os.environ.get("GAZE_ENGINE_UUID", "unknown")
    uptime_ms = int((datetime.now() - _start_time).total_seconds() * 1000)

    # Check if models are ready
    models_ready, missing_models = check_models_downloaded()

    # Check external dependencies
    ffmpeg_status = get_ffmpeg_status()
    gpu_status = get_gpu_status()
    dependencies = DependencyStatus(
        ffmpeg_available=ffmpeg_status["ffmpeg_available"],
        ffmpeg_version=ffmpeg_status["ffmpeg_version"],
        ffprobe_available=ffmpeg_status["ffprobe_available"],
        ffprobe_version=ffmpeg_status["ffprobe_version"],
        gpu_available=gpu_status["gpu_available"],
        gpu_name=gpu_status["gpu_name"],
        gpu_memory_mb=gpu_status["gpu_memory_mb"],
    )

    # Determine status - error if critical dependencies missing
    if not dependencies.ffmpeg_available or not dependencies.ffprobe_available:
        status: Literal["starting", "ready", "error"] = "error"
    elif models_ready:
        status = "ready"
    else:
        status = "starting"

    return HealthResponse(
        status=status,
        models_ready=models_ready,
        missing_models=missing_models,
        dependencies=dependencies,
        engine_uuid=engine_uuid,
        uptime_ms=uptime_ms,
    )


@router.post("/shutdown")
async def shutdown(
    request: Request,
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Initiate graceful shutdown."""
    logger.info("Shutdown requested")

    # Schedule shutdown after response
    async def delayed_shutdown() -> None:
        await asyncio.sleep(0.5)
        lifecycle_manager = getattr(request.app.state, "lifecycle_manager", None)
        if lifecycle_manager:
            await lifecycle_manager.graceful_shutdown()
        else:
            os._exit(0)

    asyncio.create_task(delayed_shutdown())
    return {"status": "shutting_down"}
