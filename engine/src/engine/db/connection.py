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
    ],
    "frames": [
        ("colors", "TEXT"),
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
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY(frame_id) REFERENCES frames(frame_id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE SET NULL
);
"""

SCHEMA_INDEXES = """
-- Indexes (run after migrations to ensure columns exist)
CREATE INDEX IF NOT EXISTS idx_videos_library ON videos(library_id);
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
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);
"""
