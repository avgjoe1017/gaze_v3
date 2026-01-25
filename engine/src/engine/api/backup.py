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
    recognition_mode: str | None = None  # 'average', 'reference_only', 'weighted'
    created_at_ms: int
    updated_at_ms: int


class BackupFaceReference(BaseModel):
    """Reference faces marked by users as canonical examples."""
    face_id: str
    person_id: str
    weight: float
    created_at_ms: int


class BackupFaceNegative(BaseModel):
    """Negative examples: faces that should NOT match a person."""
    face_id: str
    person_id: str
    created_at_ms: int


class BackupPersonPairThreshold(BaseModel):
    """Per-person-pair thresholds for frequently confused pairs."""
    person_a_id: str
    person_b_id: str
    threshold: float
    correction_count: int
    created_at_ms: int
    updated_at_ms: int


class BackupMediaFavorite(BaseModel):
    media_id: str
    created_at_ms: int


class BackupPersonFavorite(BaseModel):
    person_id: str
    created_at_ms: int


class BackupMediaTag(BaseModel):
    media_id: str
    tag: str
    created_at_ms: int


class BackupPayload(BaseModel):
    """Complete metadata backup payload."""
    # Schema version for migration support
    schema_version: str = "1.0"  # Increment when schema changes
    app_version: str = "3.0.0"  # App version that created this backup
    created_at_ms: int
    created_at_iso: str  # Human-readable timestamp
    
    # User data (the stuff users care about)
    settings: dict[str, Any]  # All app settings and indexing presets
    libraries: list[BackupLibrary]  # Library paths and configuration
    persons: list[BackupPerson]  # Face person names
    face_references: list[BackupFaceReference] = []  # Reference faces (canonical examples)
    face_negatives: list[BackupFaceNegative] = []  # Negative examples (not this person)
    person_pair_thresholds: list[BackupPersonPairThreshold] = []  # Person merge/confusion thresholds
    media_favorites: list[BackupMediaFavorite] = []  # User favorites for media
    person_favorites: list[BackupPersonFavorite] = []  # User favorites for persons
    media_tags: list[BackupMediaTag] = []  # User tags
    
    # Media metadata (for recovery and search)
    media: list[BackupMedia]
    media_metadata: list[BackupMediaMetadata]
    videos: list[BackupVideo]
    video_metadata: list[BackupVideoMetadata]
    
    # Migration info
    migration_notes: str | None = None  # Notes about schema changes or migration steps


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
    media_favorites: list[BackupMediaFavorite] = []
    person_favorites: list[BackupPersonFavorite] = []
    media_tags: list[BackupMediaTag] = []

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
            SELECT person_id, name, thumbnail_face_id, face_count, recognition_mode, created_at_ms, updated_at_ms
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
                recognition_mode=row.get("recognition_mode"),  # May be None for old data
                created_at_ms=row["created_at_ms"],
                updated_at_ms=row["updated_at_ms"],
            )
            for row in rows
        ]

        # Face references (canonical examples)
        cursor = await db.execute(
            """
            SELECT face_id, person_id, weight, created_at_ms
            FROM face_references
            """
        )
        rows = await cursor.fetchall()
        face_references = [
            BackupFaceReference(
                face_id=row["face_id"],
                person_id=row["person_id"],
                weight=row["weight"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        # Face negatives (not this person)
        cursor = await db.execute(
            """
            SELECT face_id, person_id, created_at_ms
            FROM face_negatives
            """
        )
        rows = await cursor.fetchall()
        face_negatives = [
            BackupFaceNegative(
                face_id=row["face_id"],
                person_id=row["person_id"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        # Person pair thresholds (for merges/confusion handling)
        cursor = await db.execute(
            """
            SELECT person_a_id, person_b_id, threshold, correction_count, created_at_ms, updated_at_ms
            FROM person_pair_thresholds
            """
        )
        rows = await cursor.fetchall()
        person_pair_thresholds = [
            BackupPersonPairThreshold(
                person_a_id=row["person_a_id"],
                person_b_id=row["person_b_id"],
                threshold=row["threshold"],
                correction_count=row["correction_count"],
                created_at_ms=row["created_at_ms"],
                updated_at_ms=row["updated_at_ms"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT media_id, created_at_ms
            FROM media_favorites
            """
        )
        rows = await cursor.fetchall()
        media_favorites = [
            BackupMediaFavorite(
                media_id=row["media_id"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT person_id, created_at_ms
            FROM person_favorites
            """
        )
        rows = await cursor.fetchall()
        person_favorites = [
            BackupPersonFavorite(
                person_id=row["person_id"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        cursor = await db.execute(
            """
            SELECT media_id, tag, created_at_ms
            FROM media_tags
            """
        )
        rows = await cursor.fetchall()
        media_tags = [
            BackupMediaTag(
                media_id=row["media_id"],
                tag=row["tag"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

    now = datetime.now()
    now_ms = int(now.timestamp() * 1000)
    now_iso = now.isoformat()

    return BackupPayload(
        schema_version="1.0",
        app_version="3.0.0",
        created_at_ms=now_ms,
        created_at_iso=now_iso,
        settings=settings,
        libraries=libraries,
        persons=persons,
        face_references=face_references,
        face_negatives=face_negatives,
        person_pair_thresholds=person_pair_thresholds,
        media_favorites=media_favorites,
        person_favorites=person_favorites,
        media_tags=media_tags,
        media=media,
        media_metadata=media_metadata,
        videos=videos,
        video_metadata=video_metadata,
        migration_notes="Schema v1.0: Includes all user data (tags, favorites, face names, settings). "
                        "Face recognition data includes references, negatives, and pair thresholds.",
    )


@router.post("/restore")
async def restore_backup(
    payload: BackupPayload,
    mode: Literal["merge", "replace"] = Query("merge"),
    skip_missing_paths: bool = Query(False, description="Skip libraries with missing paths instead of failing"),
    _token: str = Depends(verify_token),
) -> dict[str, Any]:
    """
    Restore metadata backup into the database.
    
    Args:
        payload: Backup payload to restore
        mode: "merge" (preserve existing) or "replace" (wipe and import)
        skip_missing_paths: If True, skip libraries where folder_path doesn't exist (for recovery scenarios)
    
    Returns:
        Restore result with statistics and any warnings
    """
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="Invalid restore mode")
    
    from pathlib import Path
    
    restore_stats = {
        "libraries_restored": 0,
        "libraries_skipped": 0,
        "libraries_missing_paths": [],
        "settings_restored": 0,
        "persons_restored": 0,
        "face_references_restored": 0,
        "face_negatives_restored": 0,
        "person_pair_thresholds_restored": 0,
        "media_favorites_restored": 0,
        "person_favorites_restored": 0,
        "media_tags_restored": 0,
        "media_restored": 0,
        "videos_restored": 0,
    }

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
            await db.execute("DELETE FROM media_tags")
            await db.execute("DELETE FROM media_favorites")
            await db.execute("DELETE FROM person_favorites")
            await db.execute("DELETE FROM videos")
            await db.execute("DELETE FROM media")
            await db.execute("DELETE FROM jobs")
            await db.execute("DELETE FROM settings")
            await db.execute("DELETE FROM libraries")

        # Restore settings (all app settings and indexing presets)
        for key, value in payload.settings.items():
            await db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, json.dumps(value)),
            )
            restore_stats["settings_restored"] += 1

        # Restore libraries with path validation
        for library in payload.libraries:
            # Check if path exists (for recovery scenarios)
            path_exists = Path(library.folder_path).exists()
            
            if not path_exists and not skip_missing_paths:
                # In strict mode, fail if path doesn't exist
                raise HTTPException(
                    status_code=400,
                    detail=f"Library path does not exist: {library.folder_path}. "
                           "Use skip_missing_paths=true to skip missing paths.",
                )
            
            if not path_exists and skip_missing_paths:
                # In recovery mode, skip but record it
                restore_stats["libraries_skipped"] += 1
                restore_stats["libraries_missing_paths"].append({
                    "library_id": library.library_id,
                    "folder_path": library.folder_path,
                    "name": library.name,
                })
                logger.warning(f"Skipping library with missing path: {library.folder_path}")
                continue
            
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
            restore_stats["libraries_restored"] += 1

        # Restore media and videos (before persons, since persons reference faces which reference videos)
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
            restore_stats["media_restored"] += 1

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
            restore_stats["videos_restored"] += 1

        for meta in payload.video_metadata:
            await db.execute(
                """
                INSERT INTO video_metadata (video_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(video_id, key) DO UPDATE SET value = excluded.value
                """,
                (meta.video_id, meta.key, meta.value),
            )

        # Restore persons (face names)
        for person in payload.persons:
            # Handle backwards compatibility: old backups may not have recognition_mode
            recognition_mode = getattr(person, "recognition_mode", None) or "average"
            await db.execute(
                """
                INSERT INTO persons (person_id, name, thumbnail_face_id, face_count, recognition_mode, created_at_ms, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    name = excluded.name,
                    thumbnail_face_id = excluded.thumbnail_face_id,
                    face_count = excluded.face_count,
                    recognition_mode = excluded.recognition_mode,
                    created_at_ms = excluded.created_at_ms,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    person.person_id,
                    person.name,
                    person.thumbnail_face_id,
                    person.face_count,
                    recognition_mode,
                    person.created_at_ms,
                    person.updated_at_ms,
                ),
            )
            restore_stats["persons_restored"] += 1

        # Restore face references (canonical examples for face recognition)
        for ref in payload.face_references:
            await db.execute(
                """
                INSERT INTO face_references (face_id, person_id, weight, created_at_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(face_id, person_id) DO UPDATE SET
                    weight = excluded.weight,
                    created_at_ms = excluded.created_at_ms
                """,
                (ref.face_id, ref.person_id, ref.weight, ref.created_at_ms),
            )
            restore_stats["face_references_restored"] += 1

        # Restore face negatives (not this person)
        for neg in payload.face_negatives:
            await db.execute(
                """
                INSERT INTO face_negatives (face_id, person_id, created_at_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(face_id, person_id) DO UPDATE SET created_at_ms = excluded.created_at_ms
                """,
                (neg.face_id, neg.person_id, neg.created_at_ms),
            )
            restore_stats["face_negatives_restored"] += 1

        # Restore person pair thresholds (for merges/confusion handling)
        for threshold in payload.person_pair_thresholds:
            await db.execute(
                """
                INSERT INTO person_pair_thresholds (person_a_id, person_b_id, threshold, correction_count, created_at_ms, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(person_a_id, person_b_id) DO UPDATE SET
                    threshold = excluded.threshold,
                    correction_count = excluded.correction_count,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    threshold.person_a_id,
                    threshold.person_b_id,
                    threshold.threshold,
                    threshold.correction_count,
                    threshold.created_at_ms,
                    threshold.updated_at_ms,
                ),
            )
            restore_stats["person_pair_thresholds_restored"] += 1

        # Restore user favorites and tags
        for favorite in payload.media_favorites:
            await db.execute(
                """
                INSERT INTO media_favorites (media_id, created_at_ms)
                VALUES (?, ?)
                ON CONFLICT(media_id) DO UPDATE SET created_at_ms = excluded.created_at_ms
                """,
                (favorite.media_id, favorite.created_at_ms),
            )
            restore_stats["media_favorites_restored"] += 1

        for favorite in payload.person_favorites:
            await db.execute(
                """
                INSERT INTO person_favorites (person_id, created_at_ms)
                VALUES (?, ?)
                ON CONFLICT(person_id) DO UPDATE SET created_at_ms = excluded.created_at_ms
                """,
                (favorite.person_id, favorite.created_at_ms),
            )
            restore_stats["person_favorites_restored"] += 1

        for tag in payload.media_tags:
            await db.execute(
                """
                INSERT INTO media_tags (media_id, tag, created_at_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(media_id, tag) DO UPDATE SET created_at_ms = excluded.created_at_ms
                """,
                (tag.media_id, tag.tag, tag.created_at_ms),
            )
            restore_stats["media_tags_restored"] += 1
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
            restore_stats["videos_restored"] += 1

        await db.commit()

    logger.info(f"Backup restored (mode={mode}, schema_version={payload.schema_version})")
    
    result = {
        "status": "ok",
        "mode": mode,
        "schema_version": payload.schema_version,
        "app_version": payload.app_version,
        "backup_created_at": payload.created_at_iso,
        "stats": restore_stats,
    }
    
    if restore_stats["libraries_missing_paths"]:
        result["warnings"] = [
            f"Library '{lib['name'] or lib['library_id']}' skipped: path '{lib['folder_path']}' does not exist"
            for lib in restore_stats["libraries_missing_paths"]
        ]
    
    return result
