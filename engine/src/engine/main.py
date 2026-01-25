"""Gaze Engine - FastAPI application entry point."""

import argparse
import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .api import health, models, libraries, videos, media, search, jobs, settings, logs, stats, assets, faces, backup, network, maintenance, favorites
from .ws.handler import websocket_handler
from .core.lifecycle import LifecycleManager, repair_consistency
from .core.indexer import auto_continue_indexing
from .db.connection import init_database
from .middleware.origin import OriginValidationMiddleware
from .utils.logging import setup_logging, get_logger
from .utils.paths import get_data_dir

logger = get_logger(__name__)

# Global state
ENGINE_UUID = str(uuid.uuid4())
START_TIME = datetime.now()
lifecycle_manager: LifecycleManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    global lifecycle_manager

    logger.info(f"Starting Gaze Engine {ENGINE_UUID}")

    # Initialize database
    data_dir = get_data_dir()
    db_path = data_dir / "gaze.db"
    await init_database(db_path)

    # Repair any consistency issues from crash/unclean shutdown
    await repair_consistency()

    # Initialize lifecycle manager
    lifecycle_manager = LifecycleManager(
        engine_uuid=ENGINE_UUID,
        data_dir=data_dir,
    )
    await lifecycle_manager.startup()
    app.state.lifecycle_manager = lifecycle_manager

    # Start auto-continuation background task for indexing
    asyncio.create_task(auto_continue_indexing())

    yield

    # Cleanup
    logger.info("Shutting down Gaze Engine")
    if lifecycle_manager:
        await lifecycle_manager.shutdown()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Gaze Engine",
        version="3.0.0",
        description="Privacy-first local video search engine",
        lifespan=lifespan,
    )

    # Add Origin validation middleware (before CORS)
    app.add_middleware(OriginValidationMiddleware)
    
    # Add CORS middleware - strict origin allowlist
    # Only allow Tauri app origin (tauri://localhost) and localhost for dev
    allowed_origins = [
        "tauri://localhost",  # Tauri app origin
        "http://localhost:1420",  # Dev server (only in debug mode)
    ]
    
    # In production, only allow Tauri origin
    import os
    if os.environ.get("GAZE_LOG_LEVEL", "INFO").upper() != "DEBUG":
        allowed_origins = ["tauri://localhost"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[],
        max_age=0,  # Don't cache preflight
    )

    # Include routers
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(libraries.router)
    app.include_router(videos.router)
    app.include_router(media.router)
    app.include_router(search.router)
    app.include_router(jobs.router)
    app.include_router(settings.router)
    app.include_router(logs.router)
    app.include_router(stats.router)
    app.include_router(assets.router)
    app.include_router(faces.router)
    app.include_router(backup.router)
    app.include_router(network.router)
    app.include_router(maintenance.router)
    app.include_router(favorites.router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket_handler(websocket)

    return app


def main() -> None:
    """Entry point for the engine."""
    parser = argparse.ArgumentParser(description="Gaze Engine")
    parser.add_argument("--port", type=int, default=48100, help="Port to listen on")
    parser.add_argument("--token", type=str, default="dev-token", help="Auth token")
    parser.add_argument("--parent-pid", type=int, default=None, help="Parent process PID")
    parser.add_argument("--data-dir", type=str, default=None, help="Data directory override")
    parser.add_argument("--log-level", type=str, default="INFO", help="Log level")
    args = parser.parse_args()

    # Set environment variables early (before setup_logging) so middleware can use them
    os.environ["GAZE_ENGINE_UUID"] = ENGINE_UUID
    os.environ["GAZE_AUTH_TOKEN"] = args.token
    os.environ["GAZE_PORT"] = str(args.port)  # Set port for lockfile
    os.environ["GAZE_LOG_LEVEL"] = args.log_level.upper()  # Set early for middleware
    if args.parent_pid:
        os.environ["GAZE_PARENT_PID"] = str(args.parent_pid)
    if args.data_dir:
        os.environ["GAZE_DATA_DIR"] = args.data_dir

    # Set up logging (after env vars are set)
    setup_logging(args.log_level)

    logger.info(f"Starting on port {args.port}")

    # Create and run app
    app = create_app()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
