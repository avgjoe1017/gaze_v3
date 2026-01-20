"""Path utilities for Gaze Engine."""

import os
import sys
from pathlib import Path


def get_data_dir() -> Path:
    """Get the data directory for Gaze.

    Priority:
    1. GAZE_DATA_DIR environment variable
    2. Platform-specific default
    """
    env_dir = os.environ.get("GAZE_DATA_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    path = base / "Gaze"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_models_dir() -> Path:
    """Get the directory for ML models."""
    path = get_data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_thumbnails_dir() -> Path:
    """Get the directory for video thumbnails."""
    path = get_data_dir() / "thumbnails"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_faiss_dir() -> Path:
    """Get the directory for FAISS index shards."""
    path = get_data_dir() / "faiss"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_temp_dir() -> Path:
    """Get the temporary directory for processing."""
    path = get_data_dir() / "temp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_lockfile_path() -> Path:
    """Get the path to the engine lockfile."""
    return get_data_dir() / "engine.lock"
