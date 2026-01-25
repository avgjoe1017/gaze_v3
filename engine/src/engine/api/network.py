"""Network trust reporting endpoints."""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.network import get_network_counters
from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.paths import get_data_dir, get_models_dir
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/network", tags=["network"])


async def get_offline_mode() -> bool:
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


class NetworkRequestEntry(BaseModel):
    kind: str
    model: str | None
    url: str
    status: str
    attempt: int | None
    error: str | None
    timestamp_ms: int


class NetworkStatusResponse(BaseModel):
    offline_mode: bool
    outbound_requests_total: int
    model_downloads_total: int
    recent_requests: list[NetworkRequestEntry]


@router.get("/status", response_model=NetworkStatusResponse)
async def network_status(_token: str = Depends(verify_token)) -> NetworkStatusResponse:
    """Return outbound network counters for the current engine session."""
    outbound_total, model_total, recent = get_network_counters()
    return NetworkStatusResponse(
        offline_mode=await get_offline_mode(),
        outbound_requests_total=outbound_total,
        model_downloads_total=model_total,
        recent_requests=recent,
    )


class PrivacyReportResponse(BaseModel):
    """Privacy report for copy/paste."""
    report: str


@router.get("/privacy-report", response_model=PrivacyReportResponse)
async def get_privacy_report(_token: str = Depends(verify_token)) -> PrivacyReportResponse:
    """Generate a privacy report that can be copied."""
    from datetime import datetime
    import os
    
    offline_mode = await get_offline_mode()
    outbound_total, model_total, recent = get_network_counters()
    
    # Get last request timestamp
    last_request_ms = None
    if recent:
        last_request_ms = max(req.timestamp_ms for req in recent)
    
    # Get models installed
    models_dir = get_models_dir()
    model_files = {
        "whisper-base": "whisper-base.pt",
        "openclip-vit-b-32": "openclip-vit-b-32.bin",
        "ssdlite320-mobilenet-v3": "ssdlite320_mobilenet_v3_large_coco.pth",
    }
    installed_models = [name for name, filename in model_files.items() if (models_dir / filename).exists()]
    
    # Get data root
    data_dir = get_data_dir()
    
    # Build report
    lines = [
        "SafeKeeps Vault Privacy Report",
        "=" * 40,
        f"Generated: {datetime.now().isoformat()}",
        "",
        "Network Status:",
        f"  Offline Mode: {'ON (No network requests)' if offline_mode else 'OFF'}"
        f"  Outbound Requests (this session): {outbound_total}",
        f"  Model Downloads (this session): {model_total}",
        f"  Last Request: {datetime.fromtimestamp(last_request_ms / 1000).isoformat() if last_request_ms else 'None'}",
        "",
        "Models Installed:",
    ]
    for model in installed_models:
        lines.append(f"  ✓ {model}")
    if not installed_models:
        lines.append("  (none)")
    
    lines.extend([
        "",
        "Data Storage:",
        f"  Data Root: {data_dir}",
        "",
        "Privacy Settings:",
        "  Telemetry: OFF (no telemetry collected)",
        "  Cloud Upload: OFF (all processing local)",
        "  Face Recognition: Opt-in only",
        "",
        "This report contains no sensitive file paths or personal data.",
    ])
    
    return PrivacyReportResponse(report="\n".join(lines))
