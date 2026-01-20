"""Network trust reporting endpoints."""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.network import get_network_counters
from ..db.connection import get_db
from ..middleware.auth import verify_token

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
