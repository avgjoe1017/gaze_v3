"""Settings endpoints."""

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Default settings
DEFAULT_SETTINGS = {
    "max_concurrent_jobs": 2,
    "thumbnail_quality": 85,
    "frame_interval_seconds": 2.0,
    "faiss_cache_max": 8,
    "indexing_preset": "deep",
    "prioritize_recent_media": False,
    "transcription_model": "base",
    "transcription_language": None,
    "transcription_backend": "auto",
    "transcription_vad_enabled": True,
    "transcription_min_silence_ms": 500,
    "transcription_silence_threshold_db": -35,
    "transcription_chunk_seconds": 30.0,
    "offline_mode": False,
    "face_recognition_enabled": False,
}


class Settings(BaseModel):
    """Settings model."""

    max_concurrent_jobs: int = 2
    thumbnail_quality: int = 85
    frame_interval_seconds: float = 2.0
    faiss_cache_max: int = 8
    indexing_preset: str = "deep"
    prioritize_recent_media: bool = False
    transcription_model: str = "base"
    transcription_language: str | None = None
    transcription_backend: str = "auto"
    transcription_vad_enabled: bool = True
    transcription_min_silence_ms: int = 500
    transcription_silence_threshold_db: int = -35
    transcription_chunk_seconds: float | None = 30.0
    offline_mode: bool = False
    face_recognition_enabled: bool = False


class SettingsUpdate(BaseModel):
    """Settings update request."""

    max_concurrent_jobs: int | None = None
    thumbnail_quality: int | None = None
    frame_interval_seconds: float | None = None
    faiss_cache_max: int | None = None
    indexing_preset: str | None = None
    prioritize_recent_media: bool | None = None
    transcription_model: str | None = None
    transcription_language: str | None = None
    transcription_backend: str | None = None
    transcription_vad_enabled: bool | None = None
    transcription_min_silence_ms: int | None = None
    transcription_silence_threshold_db: int | None = None
    transcription_chunk_seconds: float | None = None
    offline_mode: bool | None = None
    face_recognition_enabled: bool | None = None


@router.get("", response_model=Settings)
async def get_settings(_token: str = Depends(verify_token)) -> Settings:
    """Get all settings."""
    settings = dict(DEFAULT_SETTINGS)

    async for db in get_db():
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()

        for row in rows:
            key = row["key"]
            if key in settings:
                # Parse JSON value
                try:
                    settings[key] = json.loads(row["value"])
                except json.JSONDecodeError:
                    settings[key] = row["value"]

    return Settings(**settings)


@router.patch("", response_model=Settings)
async def update_settings(update: SettingsUpdate, _token: str = Depends(verify_token)) -> Settings:
    """Update settings."""
    async for db in get_db():
        # Update each provided setting
        update_data = update.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            json_value = json.dumps(value)
            await db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, json_value),
            )

        await db.commit()
        logger.info(f"Updated settings: {update_data}")

    # Return updated settings
    return await get_settings()
