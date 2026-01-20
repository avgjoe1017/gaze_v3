"""Backup and restore endpoints (metadata-only)."""

import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])


class BackupLibrary(BaseModel):
    library_id: str
    folder_path: str
    name: str | None = None
    recursive: bool
    created_at_ms: int


class BackupMedia(BaseModel):
    media_id: str
    library_id: str
    path: str
    filename: str
    file_ext: str | None = None
    media_type: str
    file_size: int
    mtime_ms: int
    fingerprint: str
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    creation_time: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    status: str
    progress: float
    error_code: str | None = None
    error_message: str | None = None
    indexed_at_ms: int | None = None
    created_at_ms: int


class BackupMediaMetadata(BaseModel):
    media_id: str
    key: str
    value: str | None = None


class BackupVideo(BaseModel):
    video_id: str
    library_id: str
    path: str
    filename: str
    media_type: str
    file_size: int
    mtime_ms: int
    fingerprint: str
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    video_bitrate: int | None = None
    audio_codec: str | None = None
    audio_channels: int | None = None
    audio_sample_rate: int | None = None
    container_format: str | None = None
    rotation: int = 0
    creation_time: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    status: str
    last_completed_stage: str | None = None
    progress: float
    error_code: str | None = None
    error_message: str | None = None
    language_code: str | None = None
    indexed_at_ms: int | None = None
    created_at_ms: int


class BackupVideoMetadata(BaseModel):
    video_id: str
    key: str
    value: str | None = None


class BackupPerson(BaseModel):
    person_id: str
    name: str
    thumbnail_face_id: str | None = None
    face_count: int
    created_at_ms: int
    updated_at_ms: int


class BackupPayload(BaseModel):
    version: str
    created_at_ms: int
    settings: dict[str, Any]
    libraries: list[BackupLibrary]
    media: list[BackupMedia]
    media_metadata: list[BackupMediaMetadata]
    videos: list[BackupVideo]
    video_metadata: list[BackupVideoMetadata]
    persons: list[BackupPerson]


@router.get("/export", response_model=BackupPayload)
async def export_backup(_token: str = Depends(verify_token)) -> BackupPayload:
    """Export metadata-only backup."""
    settings: dict[str, Any] = {}
    libraries: list[BackupLibrary] = []
    media: list[BackupMedia] = []
    media_metadata: list[BackupMediaMetadata] = []
    videos: list[BackupVideo] = []
    video_metadata: list[BackupVideoMetadata] = []
    persons: list[BackupPerson] = []

    async for db in get_db():
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        for row in rows:
            try:
                settings[row["key"]] = json.loads(row["value"])
            except Exception:
                settings[row["key"]] = row["value"]

        cursor = await db.execute(
            """
            SELECT library_id, folder_path, name, recursive, created_at_ms
            FROM libraries
            ORDER BY created_at_ms DESC
            """
        )
        rows = await cursor.fetchall()
        libraries = [
            BackupLibrary(
                library_id=row["library_id"],
                folder_path=row["folder_path"],
                name=row["name"],
                recursive=bool(row["recursive"]),
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT
                media_id, library_id, path, filename, file_ext, media_type,
                file_size, mtime_ms, fingerprint, duration_ms, width, height,
                creation_time, camera_make, camera_model, gps_lat, gps_lng,
                status, progress, error_code, error_message, indexed_at_ms, created_at_ms
            FROM media
            """
        )
        rows = await cursor.fetchall()
        media = [
            BackupMedia(
                media_id=row["media_id"],
                library_id=row["library_id"],
                path=row["path"],
                filename=row["filename"],
                file_ext=row["file_ext"],
                media_type=row["media_type"],
                file_size=row["file_size"],
                mtime_ms=row["mtime_ms"],
                fingerprint=row["fingerprint"],
                duration_ms=row["duration_ms"],
                width=row["width"],
                height=row["height"],
                creation_time=row["creation_time"],
                camera_make=row["camera_make"],
                camera_model=row["camera_model"],
                gps_lat=row["gps_lat"],
                gps_lng=row["gps_lng"],
                status=row["status"],
                progress=row["progress"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                indexed_at_ms=row["indexed_at_ms"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT media_id, key, value
            FROM media_metadata
            """
        )
        rows = await cursor.fetchall()
        media_metadata = [
            BackupMediaMetadata(
                media_id=row["media_id"],
                key=row["key"],
                value=row["value"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT
                video_id, library_id, path, filename, media_type, file_size,
                mtime_ms, fingerprint, duration_ms, width, height,
                fps, video_codec, video_bitrate,
                audio_codec, audio_channels, audio_sample_rate,
                container_format, rotation,
                creation_time, camera_make, camera_model,
                gps_lat, gps_lng,
                status, last_completed_stage, progress, error_code, error_message,
                language_code, indexed_at_ms, created_at_ms
            FROM videos
            """
        )
        rows = await cursor.fetchall()
        videos = [
            BackupVideo(
                video_id=row["video_id"],
                library_id=row["library_id"],
                path=row["path"],
                filename=row["filename"],
                media_type=row["media_type"],
                file_size=row["file_size"],
                mtime_ms=row["mtime_ms"],
                fingerprint=row["fingerprint"],
                duration_ms=row["duration_ms"],
                width=row["width"],
                height=row["height"],
                fps=row["fps"],
                video_codec=row["video_codec"],
                video_bitrate=row["video_bitrate"],
                audio_codec=row["audio_codec"],
                audio_channels=row["audio_channels"],
                audio_sample_rate=row["audio_sample_rate"],
                container_format=row["container_format"],
                rotation=row["rotation"] or 0,
                creation_time=row["creation_time"],
                camera_make=row["camera_make"],
                camera_model=row["camera_model"],
                gps_lat=row["gps_lat"],
                gps_lng=row["gps_lng"],
                status=row["status"],
                last_completed_stage=row["last_completed_stage"],
                progress=row["progress"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                language_code=row["language_code"],
                indexed_at_ms=row["indexed_at_ms"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT video_id, key, value
            FROM video_metadata
            """
        )
        rows = await cursor.fetchall()
        video_metadata = [
            BackupVideoMetadata(
                video_id=row["video_id"],
                key=row["key"],
                value=row["value"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT person_id, name, thumbnail_face_id, face_count, created_at_ms, updated_at_ms
            FROM persons
            """
        )
        rows = await cursor.fetchall()
        persons = [
            BackupPerson(
                person_id=row["person_id"],
                name=row["name"],
                thumbnail_face_id=row["thumbnail_face_id"],
                face_count=row["face_count"],
                created_at_ms=row["created_at_ms"],
                updated_at_ms=row["updated_at_ms"],
            )
            for row in rows
        ]

    return BackupPayload(
        version="1.0",
        created_at_ms=int(datetime.now().timestamp() * 1000),
        settings=settings,
        libraries=libraries,
        media=media,
        media_metadata=media_metadata,
        videos=videos,
        video_metadata=video_metadata,
        persons=persons,
    )


@router.post("/restore")
async def restore_backup(
    payload: BackupPayload,
    mode: Literal["merge", "replace"] = Query("merge"),
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Restore metadata backup into the database."""
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="Invalid restore mode")

    async for db in get_db():
        if mode == "replace":
            await db.execute("DELETE FROM faces")
            await db.execute("DELETE FROM persons")
            await db.execute("DELETE FROM detections")
            await db.execute("DELETE FROM frames")
            await db.execute("DELETE FROM transcript_segments")
            await db.execute("DELETE FROM transcript_fts")
            await db.execute("DELETE FROM video_metadata")
            await db.execute("DELETE FROM media_metadata")
            await db.execute("DELETE FROM videos")
            await db.execute("DELETE FROM media")
            await db.execute("DELETE FROM jobs")
            await db.execute("DELETE FROM settings")
            await db.execute("DELETE FROM libraries")

        for key, value in payload.settings.items():
            await db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, json.dumps(value)),
            )

        for library in payload.libraries:
            await db.execute(
                """
                INSERT INTO libraries (library_id, folder_path, name, recursive, created_at_ms)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(library_id) DO UPDATE SET
                    folder_path = excluded.folder_path,
                    name = excluded.name,
                    recursive = excluded.recursive,
                    created_at_ms = excluded.created_at_ms
                """,
                (
                    library.library_id,
                    library.folder_path,
                    library.name,
                    int(library.recursive),
                    library.created_at_ms,
                ),
            )

        for item in payload.media:
            await db.execute(
                """
                INSERT INTO media (
                    media_id, library_id, path, filename, file_ext, media_type,
                    file_size, mtime_ms, fingerprint, duration_ms, width, height,
                    creation_time, camera_make, camera_model, gps_lat, gps_lng,
                    status, progress, error_code, error_message, indexed_at_ms, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_id) DO UPDATE SET
                    library_id = excluded.library_id,
                    path = excluded.path,
                    filename = excluded.filename,
                    file_ext = excluded.file_ext,
                    media_type = excluded.media_type,
                    file_size = excluded.file_size,
                    mtime_ms = excluded.mtime_ms,
                    fingerprint = excluded.fingerprint,
                    duration_ms = excluded.duration_ms,
                    width = excluded.width,
                    height = excluded.height,
                    creation_time = excluded.creation_time,
                    camera_make = excluded.camera_make,
                    camera_model = excluded.camera_model,
                    gps_lat = excluded.gps_lat,
                    gps_lng = excluded.gps_lng,
                    status = excluded.status,
                    progress = excluded.progress,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    indexed_at_ms = excluded.indexed_at_ms,
                    created_at_ms = excluded.created_at_ms
                """,
                (
                    item.media_id,
                    item.library_id,
                    item.path,
                    item.filename,
                    item.file_ext,
                    item.media_type,
                    item.file_size,
                    item.mtime_ms,
                    item.fingerprint,
                    item.duration_ms,
                    item.width,
                    item.height,
                    item.creation_time,
                    item.camera_make,
                    item.camera_model,
                    item.gps_lat,
                    item.gps_lng,
                    item.status,
                    item.progress,
                    item.error_code,
                    item.error_message,
                    item.indexed_at_ms,
                    item.created_at_ms,
                ),
            )

        for meta in payload.media_metadata:
            await db.execute(
                """
                INSERT INTO media_metadata (media_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(media_id, key) DO UPDATE SET value = excluded.value
                """,
                (meta.media_id, meta.key, meta.value),
            )

        for video in payload.videos:
            await db.execute(
                """
                INSERT INTO videos (
                    video_id, library_id, path, filename, media_type, file_size,
                    mtime_ms, fingerprint, duration_ms, width, height,
                    fps, video_codec, video_bitrate,
                    audio_codec, audio_channels, audio_sample_rate,
                    container_format, rotation,
                    creation_time, camera_make, camera_model,
                    gps_lat, gps_lng,
                    status, last_completed_stage, progress, error_code, error_message,
                    language_code, indexed_at_ms, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    library_id = excluded.library_id,
                    path = excluded.path,
                    filename = excluded.filename,
                    media_type = excluded.media_type,
                    file_size = excluded.file_size,
                    mtime_ms = excluded.mtime_ms,
                    fingerprint = excluded.fingerprint,
                    duration_ms = excluded.duration_ms,
                    width = excluded.width,
                    height = excluded.height,
                    fps = excluded.fps,
                    video_codec = excluded.video_codec,
                    video_bitrate = excluded.video_bitrate,
                    audio_codec = excluded.audio_codec,
                    audio_channels = excluded.audio_channels,
                    audio_sample_rate = excluded.audio_sample_rate,
                    container_format = excluded.container_format,
                    rotation = excluded.rotation,
                    creation_time = excluded.creation_time,
                    camera_make = excluded.camera_make,
                    camera_model = excluded.camera_model,
                    gps_lat = excluded.gps_lat,
                    gps_lng = excluded.gps_lng,
                    status = excluded.status,
                    last_completed_stage = excluded.last_completed_stage,
                    progress = excluded.progress,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    language_code = excluded.language_code,
                    indexed_at_ms = excluded.indexed_at_ms,
                    created_at_ms = excluded.created_at_ms
                """,
                (
                    video.video_id,
                    video.library_id,
                    video.path,
                    video.filename,
                    video.media_type,
                    video.file_size,
                    video.mtime_ms,
                    video.fingerprint,
                    video.duration_ms,
                    video.width,
                    video.height,
                    video.fps,
                    video.video_codec,
                    video.video_bitrate,
                    video.audio_codec,
                    video.audio_channels,
                    video.audio_sample_rate,
                    video.container_format,
                    video.rotation,
                    video.creation_time,
                    video.camera_make,
                    video.camera_model,
                    video.gps_lat,
                    video.gps_lng,
                    video.status,
                    video.last_completed_stage,
                    video.progress,
                    video.error_code,
                    video.error_message,
                    video.language_code,
                    video.indexed_at_ms,
                    video.created_at_ms,
                ),
            )

        for meta in payload.video_metadata:
            await db.execute(
                """
                INSERT INTO video_metadata (video_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(video_id, key) DO UPDATE SET value = excluded.value
                """,
                (meta.video_id, meta.key, meta.value),
            )

        for person in payload.persons:
            await db.execute(
                """
                INSERT INTO persons (person_id, name, thumbnail_face_id, face_count, created_at_ms, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    name = excluded.name,
                    thumbnail_face_id = excluded.thumbnail_face_id,
                    face_count = excluded.face_count,
                    created_at_ms = excluded.created_at_ms,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    person.person_id,
                    person.name,
                    person.thumbnail_face_id,
                    person.face_count,
                    person.created_at_ms,
                    person.updated_at_ms,
                ),
            )

        await db.commit()

    logger.info(f"Backup restored (mode={mode})")
    return {"status": "ok", "mode": mode}
