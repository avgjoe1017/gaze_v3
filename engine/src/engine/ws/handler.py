"""WebSocket handler for real-time progress updates."""

import asyncio
import os
import json
from typing import Any
from urllib.parse import parse_qs, urlparse
from weakref import WeakSet

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Active WebSocket connections
_connections: WeakSet[WebSocket] = WeakSet()

# Event queue for broadcasting
_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


def get_auth_token() -> str | None:
    """Get the auth token from environment variable."""
    return os.environ.get("GAZE_AUTH_TOKEN")


def is_dev_mode() -> bool:
    """Check if running in development mode."""
    log_level = os.environ.get("GAZE_LOG_LEVEL", "INFO").upper()
    return log_level == "DEBUG" or os.environ.get("GAZE_DEV_MODE") == "1"


def extract_token_from_websocket(websocket: WebSocket) -> str | None:
    """
    Extract token from WebSocket connection.
    
    Tries both Sec-WebSocket-Protocol header and query string.
    """
    # Try Sec-WebSocket-Protocol header first
    protocol_header = websocket.headers.get("sec-websocket-protocol", "")
    if protocol_header.startswith("gaze-token."):
        token = protocol_header[len("gaze-token."):].strip()
        return token
    
    # Fallback to query string
    query_string = websocket.url.query
    if query_string:
        query_params = parse_qs(query_string)
        if "token" in query_params:
            token = query_params["token"][0]
            return token
    
    return None


async def websocket_handler(websocket: WebSocket) -> None:
    """Handle a WebSocket connection with token authentication."""
    # Dev mode bypasses auth entirely
    if is_dev_mode():
        logger.debug("Dev mode enabled - allowing WebSocket connection without auth")
    else:
        expected_token = get_auth_token()

        # If token is required, verify it
        if expected_token:
            client_token = extract_token_from_websocket(websocket)
            if not client_token or client_token != expected_token:
                logger.warning("WebSocket connection rejected: invalid or missing token")
                await websocket.close(code=1008, reason="Authentication failed")
                return
        else:
            # No token configured - allow connection
            logger.debug("No GAZE_AUTH_TOKEN set - allowing WebSocket connection")
    
    await websocket.accept()
    
    # Echo token in protocol if provided (for validation)
    client_token = extract_token_from_websocket(websocket)
    if client_token:
        await websocket.send_json({"type": "auth_success"})
    
    _connections.add(websocket)
    logger.info(f"WebSocket connected. Total connections: {len(_connections)}")

    try:
        while True:
            # Receive messages from client (for subscriptions, etc.)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)

                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "subscribe":
                    # Handle topic subscriptions (for filtering in future)
                    topics = message.get("topics", [])
                    logger.debug(f"Client subscribed to topics: {topics}")

            except asyncio.TimeoutError:
                # Send heartbeat
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _connections.discard(websocket)


async def broadcast(event: dict[str, Any]) -> None:
    """Broadcast an event to all connected clients."""
    if not _connections:
        return

    message = json.dumps(event)
    disconnected = []

    for ws in list(_connections):
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(message)
        except Exception as e:
            logger.debug(f"Failed to send to WebSocket: {e}")
            disconnected.append(ws)

    for ws in disconnected:
        _connections.discard(ws)


async def emit_model_download_progress(
    model: str,
    progress: float,
    bytes_downloaded: int,
    bytes_total: int,
) -> None:
    """Emit model download progress event."""
    await broadcast({
        "type": "model_download_progress",
        "model": model,
        "progress": progress,
        "bytes_downloaded": bytes_downloaded,
        "bytes_total": bytes_total,
    })


async def emit_model_download_complete(model: str) -> None:
    """Emit model download complete event."""
    await broadcast({
        "type": "model_download_complete",
        "model": model,
    })


async def emit_model_download_error(model: str, error: str) -> None:
    """Emit model download error event."""
    await broadcast({
        "type": "model_download_error",
        "model": model,
        "error": error,
    })


async def emit_scan_progress(
    library_id: str,
    files_found: int,
    files_new: int,
    files_changed: int,
    files_deleted: int,
) -> None:
    """Emit scan progress event."""
    await broadcast({
        "type": "scan_progress",
        "library_id": library_id,
        "files_found": files_found,
        "files_new": files_new,
        "files_changed": files_changed,
        "files_deleted": files_deleted,
    })


async def emit_scan_complete(library_id: str, stats: dict) -> None:
    """Emit scan complete event."""
    await broadcast({
        "type": "scan_complete",
        "library_id": library_id,
        **stats,
    })


async def emit_job_progress(
    job_id: str,
    video_id: str,
    stage: str,
    progress: float,
    message: str = "",
) -> None:
    """Emit job progress event."""
    await broadcast({
        "type": "job_progress",
        "job_id": job_id,
        "video_id": video_id,
        "stage": stage,
        "progress": progress,
        "message": message,
    })


async def emit_job_complete(job_id: str, video_id: str) -> None:
    """Emit job complete event."""
    await broadcast({
        "type": "job_complete",
        "job_id": job_id,
        "video_id": video_id,
    })


async def emit_job_failed(
    job_id: str,
    video_id: str,
    stage: str,
    error_code: str,
    error_message: str,
) -> None:
    """Emit job failed event."""
    await broadcast({
        "type": "job_failed",
        "job_id": job_id,
        "video_id": video_id,
        "stage": stage,
        "error_code": error_code,
        "error_message": error_message,
    })


def get_connection_count() -> int:
    """Get the number of active WebSocket connections."""
    return len(_connections)
