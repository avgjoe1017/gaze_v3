"""Database connection management."""

import aiosqlite
from pathlib import Path
from typing import AsyncGenerator

from ..utils.logging import get_logger

logger = get_logger(__name__)

_db_path: Path | None = None
_db_connection: aiosqlite.Connection | None = None


# Columns added after initial schema (for migration)
MIGRATION_COLUMNS = {
    "videos": [
        ("media_type", "TEXT DEFAULT 'video'"),
        ("fps", "REAL"),
        ("video_codec", "TEXT"),
        ("video_bitrate", "INTEGER"),
        ("audio_codec", "TEXT"),
        ("audio_channels", "INTEGER"),
        ("audio_sample_rate", "INTEGER"),
        ("container_format", "TEXT"),
        ("rotation", "INTEGER DEFAULT 0"),
        ("creation_time", "TEXT"),
        ("camera_make", "TEXT"),
        ("camera_model", "TEXT"),
        ("gps_lat", "REAL"),
        ("gps_lng", "REAL"),
        ("transcript", "TEXT"),
    ],
    "frames": [
        ("colors", "TEXT"),
    ],
    "faces": [
        ("assignment_source", "TEXT DEFAULT 'legacy'"),
        ("assignment_confidence", "REAL"),
        ("assigned_at_ms", "INTEGER"),
    ],
    "persons": [
        ("recognition_mode", "TEXT DEFAULT 'average'"),
    ],
    "media": [
        ("is_live_photo_component", "INTEGER DEFAULT 0"),
        ("live_photo_pair_id", "TEXT"),
    ],
}


async def _migrate_schema(db: aiosqlite.Connection) -> None:
    """Add missing columns to existing tables."""
    for table_name, columns in MIGRATION_COLUMNS.items():
        # Get existing columns
        cursor = await db.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()
        existing_columns = {row[1] for row in rows}  # Column name is at index 1

        # Add missing columns
        for col_name, col_type in columns:
            if col_name not in existing_columns:
                try:
                    await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to {table_name}")
                except Exception as e:
                    logger.warning(f"Failed to add column {col_name} to {table_name}: {e}")


async def init_database(path: Path) -> None:
    """Initialize the database with schema."""
    global _db_path, _db_connection

    _db_path = path
    logger.info(f"Initializing database at {path}")

    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        # Enable WAL mode and other pragmas
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA busy_timeout = 5000")

        # Create tables first (without indexes on migration columns)
        await db.executescript(SCHEMA_TABLES)

        # Run migrations for existing databases
        await _migrate_schema(db)

        # Create indexes after migrations (safe now that columns exist)
        await db.executescript(SCHEMA_INDEXES)

        # Backfill media table for existing videos (safe on first run too)
        await _backfill_media_from_videos(db)

        # Backfill face assignment sources for existing data
        await _backfill_face_assignment_sources(db)

        await db.commit()

    logger.info("Database initialized")


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get a database connection."""
    if _db_path is None:
        raise RuntimeError("Database not initialized")

    async with aiosqlite.connect(_db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 30000")  # 30 second timeout
        yield db


SCHEMA_TABLES = """
CREATE TABLE IF NOT EXISTS libraries (
    library_id TEXT PRIMARY KEY,
    folder_path TEXT NOT NULL UNIQUE,
    name TEXT,
    recursive INTEGER NOT NULL DEFAULT 1,
    created_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'video',
    file_size INTEGER NOT NULL,
    mtime_ms INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    duration_ms INTEGER,
    width INTEGER,
    height INTEGER,
    -- Technical metadata
    fps REAL,
    video_codec TEXT,
    video_bitrate INTEGER,
    audio_codec TEXT,
    audio_channels INTEGER,
    audio_sample_rate INTEGER,
    container_format TEXT,
    rotation INTEGER DEFAULT 0,
    -- Source/creation metadata
    creation_time TEXT,
    camera_make TEXT,
    camera_model TEXT,
    gps_lat REAL,
    gps_lng REAL,
    -- Processing state
    status TEXT NOT NULL DEFAULT 'QUEUED',
    last_completed_stage TEXT,
    progress REAL NOT NULL DEFAULT 0.0,
    error_code TEXT,
    error_message TEXT,
    language_code TEXT,
    indexed_at_ms INTEGER,
    created_at_ms INTEGER NOT NULL,
    UNIQUE(library_id, path),
    FOREIGN KEY(library_id) REFERENCES libraries(library_id) ON DELETE CASCADE
);

-- Unified media table (photos + videos)
CREATE TABLE IF NOT EXISTS media (
    media_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_ext TEXT,
    media_type TEXT NOT NULL, -- 'video' or 'photo'
    file_size INTEGER NOT NULL,
    mtime_ms INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    duration_ms INTEGER,
    width INTEGER,
    height INTEGER,
    creation_time TEXT,
    camera_make TEXT,
    camera_model TEXT,
    gps_lat REAL,
    gps_lng REAL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    progress REAL NOT NULL DEFAULT 0.0,
    error_code TEXT,
    error_message TEXT,
    indexed_at_ms INTEGER,
    created_at_ms INTEGER NOT NULL,
    UNIQUE(library_id, path),
    FOREIGN KEY(library_id) REFERENCES libraries(library_id) ON DELETE CASCADE
);

-- Flexible key-value metadata for media
CREATE TABLE IF NOT EXISTS media_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    UNIQUE(media_id, key),
    FOREIGN KEY(media_id) REFERENCES media(media_id) ON DELETE CASCADE
);

-- Flexible key-value metadata for additional/custom fields
CREATE TABLE IF NOT EXISTS video_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    UNIQUE(video_id, key),
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
    video_id,
    start_ms UNINDEXED,
    end_ms UNINDEXED,
    text,
    tokenize="unicode61"
);

CREATE TABLE IF NOT EXISTS frames (
    frame_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    frame_index INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    thumbnail_path TEXT NOT NULL,
    colors TEXT,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS detections (
    detection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    label TEXT NOT NULL,
    confidence REAL NOT NULL,
    bbox_x REAL,
    bbox_y REAL,
    bbox_w REAL,
    bbox_h REAL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY(frame_id) REFERENCES frames(frame_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    current_stage TEXT,
    progress REAL NOT NULL DEFAULT 0.0,
    message TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Named/labeled people for face recognition
CREATE TABLE IF NOT EXISTS persons (
    person_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    thumbnail_face_id TEXT,
    face_count INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY(thumbnail_face_id) REFERENCES faces(face_id) ON DELETE SET NULL
);

-- Individual face detections with embeddings
CREATE TABLE IF NOT EXISTS faces (
    face_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    -- Bounding box
    bbox_x REAL NOT NULL,
    bbox_y REAL NOT NULL,
    bbox_w REAL NOT NULL,
    bbox_h REAL NOT NULL,
    confidence REAL NOT NULL,
    -- Face embedding (512-dim float32 = 2048 bytes)
    embedding BLOB NOT NULL,
    -- Face crop image path
    crop_path TEXT,
    -- Optional attributes
    age INTEGER,
    gender TEXT,
    -- Link to named person (null = unassigned)
    person_id TEXT,
    -- Cluster ID for auto-grouping (before manual assignment)
    cluster_id TEXT,
    -- Learning system fields
    assignment_source TEXT DEFAULT 'legacy',
    assignment_confidence REAL,
    assigned_at_ms INTEGER,
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY(frame_id) REFERENCES frames(frame_id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE SET NULL
);

-- Reference faces marked by users as canonical examples
CREATE TABLE IF NOT EXISTS face_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at_ms INTEGER NOT NULL,
    UNIQUE(face_id, person_id),
    FOREIGN KEY(face_id) REFERENCES faces(face_id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE CASCADE
);

-- Negative examples: faces that should NOT match a person
CREATE TABLE IF NOT EXISTS face_negatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    UNIQUE(face_id, person_id),
    FOREIGN KEY(face_id) REFERENCES faces(face_id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE CASCADE
);

-- Per-person-pair thresholds for frequently confused pairs
CREATE TABLE IF NOT EXISTS person_pair_thresholds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_a_id TEXT NOT NULL,
    person_b_id TEXT NOT NULL,
    threshold REAL NOT NULL DEFAULT 0.70,
    correction_count INTEGER NOT NULL DEFAULT 1,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    UNIQUE(person_a_id, person_b_id),
    FOREIGN KEY(person_a_id) REFERENCES persons(person_id) ON DELETE CASCADE,
    FOREIGN KEY(person_b_id) REFERENCES persons(person_id) ON DELETE CASCADE
);

-- User favorites for media (photos and videos)
CREATE TABLE IF NOT EXISTS media_favorites (
    media_id TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY(media_id),
    FOREIGN KEY(media_id) REFERENCES media(media_id) ON DELETE CASCADE
);

-- User favorites for persons
CREATE TABLE IF NOT EXISTS person_favorites (
    person_id TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY(person_id),
    FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE CASCADE
);

-- User tags for media (photos and videos)
CREATE TABLE IF NOT EXISTS media_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    UNIQUE(media_id, tag),
    FOREIGN KEY(media_id) REFERENCES media(media_id) ON DELETE CASCADE
);
"""

SCHEMA_INDEXES = """
-- Indexes (run after migrations to ensure columns exist)
CREATE INDEX IF NOT EXISTS idx_videos_library ON videos(library_id);
CREATE INDEX IF NOT EXISTS idx_videos_media_type ON videos(media_type);
CREATE INDEX IF NOT EXISTS idx_videos_fingerprint ON videos(fingerprint);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_creation_time ON videos(creation_time);
CREATE INDEX IF NOT EXISTS idx_videos_camera ON videos(camera_make, camera_model);
CREATE INDEX IF NOT EXISTS idx_videos_codec ON videos(video_codec);
CREATE INDEX IF NOT EXISTS idx_video_metadata ON video_metadata(video_id, key);
CREATE INDEX IF NOT EXISTS idx_segments_video ON transcript_segments(video_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_frames_video ON frames(video_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_frames_colors ON frames(colors);
CREATE INDEX IF NOT EXISTS idx_detections_video ON detections(video_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_detections_label ON detections(label);
CREATE INDEX IF NOT EXISTS idx_jobs_video ON jobs(video_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
-- Face indexes
CREATE INDEX IF NOT EXISTS idx_faces_video ON faces(video_id);
CREATE INDEX IF NOT EXISTS idx_faces_frame ON faces(frame_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_faces_cluster ON faces(cluster_id);
CREATE INDEX IF NOT EXISTS idx_faces_timestamp ON faces(video_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_faces_assignment_source ON faces(assignment_source);
CREATE INDEX IF NOT EXISTS idx_faces_assignment_confidence ON faces(assignment_confidence);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);
-- Face learning indexes
CREATE INDEX IF NOT EXISTS idx_face_references_person ON face_references(person_id);
CREATE INDEX IF NOT EXISTS idx_face_references_face ON face_references(face_id);
CREATE INDEX IF NOT EXISTS idx_face_negatives_person ON face_negatives(person_id);
CREATE INDEX IF NOT EXISTS idx_face_negatives_face ON face_negatives(face_id);
CREATE INDEX IF NOT EXISTS idx_person_pair_thresholds_a ON person_pair_thresholds(person_a_id);
CREATE INDEX IF NOT EXISTS idx_person_pair_thresholds_b ON person_pair_thresholds(person_b_id);
-- Media indexes
CREATE INDEX IF NOT EXISTS idx_media_library ON media(library_id);
CREATE INDEX IF NOT EXISTS idx_media_type ON media(media_type);
CREATE INDEX IF NOT EXISTS idx_media_fingerprint ON media(fingerprint);
CREATE INDEX IF NOT EXISTS idx_media_creation_time ON media(creation_time);
CREATE INDEX IF NOT EXISTS idx_media_metadata ON media_metadata(media_id, key);
-- User data indexes
CREATE INDEX IF NOT EXISTS idx_media_favorites_media ON media_favorites(media_id);
CREATE INDEX IF NOT EXISTS idx_person_favorites_person ON person_favorites(person_id);
CREATE INDEX IF NOT EXISTS idx_media_tags_media ON media_tags(media_id);
CREATE INDEX IF NOT EXISTS idx_media_tags_tag ON media_tags(tag);
"""


async def _backfill_face_assignment_sources(db: aiosqlite.Connection) -> None:
    """Backfill existing face assignments as 'legacy' source."""
    # Only update faces that have a person_id but no assignment_source set
    # (assignment_source would be NULL for old data before migration added the column)
    await db.execute(
        """
        UPDATE faces
        SET assignment_source = 'legacy',
            assigned_at_ms = created_at_ms
        WHERE person_id IS NOT NULL
          AND assignment_source IS NULL
        """
    )


async def _backfill_media_from_videos(db: aiosqlite.Connection) -> None:
    """Ensure media table has entries for existing videos."""
    cursor = await db.execute(
        """
        SELECT video_id, library_id, path, filename, media_type, file_size, mtime_ms, fingerprint,
               duration_ms, width, height, creation_time, camera_make, camera_model,
               gps_lat, gps_lng, status, progress, error_code, error_message,
               indexed_at_ms, created_at_ms
        FROM videos
        """
    )
    rows = await cursor.fetchall()
    for row in rows:
        path = row["path"]
        file_ext = Path(path).suffix.lower() if path else None
        await db.execute(
            """
            INSERT OR IGNORE INTO media (
                media_id, library_id, path, filename, file_ext, media_type,
                file_size, mtime_ms, fingerprint, duration_ms, width, height,
                creation_time, camera_make, camera_model, gps_lat, gps_lng,
                status, progress, error_code, error_message, indexed_at_ms, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["video_id"],
                row["library_id"],
                row["path"],
                row["filename"],
                file_ext,
                row["media_type"] or "video",
                row["file_size"],
                row["mtime_ms"],
                row["fingerprint"],
                row["duration_ms"],
                row["width"],
                row["height"],
                row["creation_time"],
                row["camera_make"],
                row["camera_model"],
                row["gps_lat"],
                row["gps_lng"],
                row["status"],
                row["progress"],
                row["error_code"],
                row["error_message"],
                row["indexed_at_ms"],
                row["created_at_ms"],
            ),
        )
