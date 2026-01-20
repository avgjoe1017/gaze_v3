"""Track outbound network activity for trust reporting."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict

NetworkStatus = Literal["started", "completed", "failed"]
NetworkKind = Literal["model_download"]


class NetworkRequest(TypedDict):
    """In-memory record of an outbound request."""

    kind: NetworkKind
    model: str | None
    url: str
    status: NetworkStatus
    attempt: int | None
    error: str | None
    timestamp_ms: int


_OUTBOUND_REQUESTS_TOTAL = 0
_MODEL_DOWNLOADS_TOTAL = 0
_RECENT_REQUESTS: list[NetworkRequest] = []
_MAX_RECENT = 50


def log_outbound_request(
    *,
    kind: NetworkKind,
    url: str,
    model: str | None = None,
    status: NetworkStatus = "started",
    attempt: int | None = None,
    error: str | None = None,
) -> None:
    """Record an outbound request for UI trust reporting."""
    global _OUTBOUND_REQUESTS_TOTAL, _MODEL_DOWNLOADS_TOTAL, _RECENT_REQUESTS

    if status == "started":
        _OUTBOUND_REQUESTS_TOTAL += 1
        if kind == "model_download":
            _MODEL_DOWNLOADS_TOTAL += 1

    entry: NetworkRequest = {
        "kind": kind,
        "model": model,
        "url": url,
        "status": status,
        "attempt": attempt,
        "error": error,
        "timestamp_ms": int(datetime.now().timestamp() * 1000),
    }

    _RECENT_REQUESTS.append(entry)
    if len(_RECENT_REQUESTS) > _MAX_RECENT:
        _RECENT_REQUESTS = _RECENT_REQUESTS[-_MAX_RECENT:]


def get_network_counters() -> tuple[int, int, list[NetworkRequest]]:
    """Return outbound counters and recent entries."""
    return _OUTBOUND_REQUESTS_TOTAL, _MODEL_DOWNLOADS_TOTAL, list(_RECENT_REQUESTS)
