"""Video indexing pipeline."""

import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

from ..db.connection import get_db
from ..ml.colors import extract_dominant_colors
from ..ml.detector import detect_objects
from ..ml.embedder import embed_image
from ..ml.whisper import transcribe_audio
from ..ml.face_detector import (
    detect_faces,
    extract_face_crop,
    get_faces_dir,
    embedding_to_bytes,
    bytes_to_embedding,
    compute_face_similarity,
)
from ..utils.ffmpeg import extract_audio, extract_frames
from ..utils.image_thumbnail import create_photo_thumbnail, create_grid_thumbnail_from_full, GRID_MAX_DIMENSION, GRID_QUALITY
from ..utils.logging import get_logger
from ..utils.paths import get_temp_dir, get_thumbnails_dir, get_faiss_dir
from ..ws.handler import emit_job_progress, emit_job_complete, emit_job_failed

logger = get_logger(__name__)

# Stage order for state machine
VIDEO_PRIMARY_STAGES = [
    "EXTRACTING_FRAMES",
    "EMBEDDING",
    "DETECTING",
    "DETECTING_FACES",
]

VIDEO_ENHANCED_STAGES = [
    "EXTRACTING_AUDIO",
    "TRANSCRIBING",
]

PHOTO_PRIMARY_STAGES = [
    "EXTRACTING_FRAMES",
    "EMBEDDING",
    "DETECTING",
    "DETECTING_FACES",
]

# Track active indexing jobs
_active_jobs: dict[str, asyncio.Task] = {}
_active_enhanced_jobs: dict[str, asyncio.Task] = {}

# Global pause flag for indexing
_indexing_paused: bool = False

# Error codes with human-readable messages
ERROR_CODES = {
    "FILE_NOT_FOUND": "The video file could not be found. It may have been moved or deleted.",
    "FFMPEG_ERROR": "FFmpeg failed to process the video. The file may be corrupted or in an unsupported format.",
    "TRANSCRIPTION_ERROR": "Speech recognition failed. The audio may be corrupted or contain no speech.",
    "EMBEDDING_ERROR": "Visual analysis failed. The video frames could not be processed.",
    "DETECTION_ERROR": "Object detection failed. The model may not be loaded correctly.",
    "FACE_DETECTION_ERROR": "Face detection failed. The model may not be loaded correctly.",
    "CANCELLED": "The indexing job was cancelled by user request.",
    "UNKNOWN_ERROR": "An unexpected error occurred during processing.",
}


async def check_job_cancelled(video_id: str) -> bool:
    """Check if a job has been cancelled."""
    async for db in get_db():
        cursor = await db.execute(
            "SELECT status FROM videos WHERE video_id = ?",
            (video_id,),
        )
        row = await cursor.fetchone()
        if row and row["status"] == "CANCELLED":
            return True
    return False


async def get_transcription_settings() -> dict[str, object]:
    """Get transcription settings with defaults."""
    defaults: dict[str, object] = {
        "transcription_language": None,
        "transcription_model": "base",
        "transcription_backend": "auto",
        "transcription_vad_enabled": True,
        "transcription_min_silence_ms": 500,
        "transcription_silence_threshold_db": -35,
        "transcription_chunk_seconds": 30.0,
    }

    keys = tuple(defaults.keys())
    async for db in get_db():
        cursor = await db.execute(
            f"""
            SELECT key, value
            FROM settings
            WHERE key IN ({",".join("?" * len(keys))})
            """,
            keys,
        )
        rows = await cursor.fetchall()
        for row in rows:
            key = row["key"]
            try:
                defaults[key] = json.loads(row["value"])
            except Exception:
                defaults[key] = row["value"]

    return defaults


async def get_indexer_settings() -> dict[str, object]:
    """Get indexing settings with defaults."""
    defaults: dict[str, object] = {
        "frame_interval_seconds": 2.0,
        "thumbnail_quality": 85,
        "max_concurrent_jobs": 2,
        "face_recognition_enabled": False,
        "indexing_preset": "deep",
        "prioritize_recent_media": False,
    }

    keys = tuple(defaults.keys())
    async for db in get_db():
        cursor = await db.execute(
            f"""
            SELECT key, value
            FROM settings
            WHERE key IN ({",".join("?" * len(keys))})
            """,
            keys,
        )
        rows = await cursor.fetchall()
        for row in rows:
            key = row["key"]
            try:
                defaults[key] = json.loads(row["value"])
            except Exception:
                defaults[key] = row["value"]

    return defaults


async def _run_with_db_retry(action: callable, *, attempts: int = 5, base_delay: float = 0.1):
    """Run a database action with retries on busy/locked errors."""
    for attempt in range(attempts):
        try:
            return await action()
        except sqlite3.OperationalError as err:
            if "locked" in str(err).lower() and attempt < attempts - 1:
                await asyncio.sleep(base_delay * (attempt + 1))
                continue
            raise


def get_primary_stage_list(media_type: str, face_recognition_enabled: bool, preset: str) -> list[str]:
    """Return primary indexing stages based on media type and settings."""
    preset = (preset or "deep").lower()
    if media_type == "video":
        if preset == "quick":
            stages = ["EXTRACTING_FRAMES", "EMBEDDING"]
        else:
            stages = VIDEO_PRIMARY_STAGES
    else:
        if preset == "quick":
            stages = ["EXTRACTING_FRAMES", "EMBEDDING"]
        else:
            stages = PHOTO_PRIMARY_STAGES
    if not face_recognition_enabled:
        stages = [stage for stage in stages if stage != "DETECTING_FACES"]
    return stages


def get_enhanced_stage_list(media_type: str, preset: str) -> list[str]:
    """Return enhanced indexing stages that run quietly after primary indexing."""
    preset = (preset or "deep").lower()
    if media_type != "video":
        return []
    if preset == "quick":
        return []
    return VIDEO_ENHANCED_STAGES


async def update_video_and_media_state(
    video_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    last_completed_stage: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    indexed_at_ms: int | None = None,
) -> None:
    """Update processing state for both videos and media tables."""
    video_fields: list[str] = []
    video_params: list[object] = []

    if status is not None:
        video_fields.append("status = ?")
        video_params.append(status)
    if progress is not None:
        video_fields.append("progress = ?")
        video_params.append(progress)
    if last_completed_stage is not None:
        video_fields.append("last_completed_stage = ?")
        video_params.append(last_completed_stage)
    if error_code is not None:
        video_fields.append("error_code = ?")
        video_params.append(error_code)
    if error_message is not None:
        video_fields.append("error_message = ?")
        video_params.append(error_message)
    if indexed_at_ms is not None:
        video_fields.append("indexed_at_ms = ?")
        video_params.append(indexed_at_ms)

    media_fields: list[str] = []
    media_params: list[object] = []

    if status is not None:
        media_fields.append("status = ?")
        media_params.append(status)
    if progress is not None:
        media_fields.append("progress = ?")
        media_params.append(progress)
    if error_code is not None:
        media_fields.append("error_code = ?")
        media_params.append(error_code)
    if error_message is not None:
        media_fields.append("error_message = ?")
        media_params.append(error_message)
    if indexed_at_ms is not None:
        media_fields.append("indexed_at_ms = ?")
        media_params.append(indexed_at_ms)

    if not video_fields and not media_fields:
        return

    async for db in get_db():
        async def _run():
            if video_fields:
                await db.execute(
                    f"UPDATE videos SET {', '.join(video_fields)} WHERE video_id = ?",
                    (*video_params, video_id),
                )
            if media_fields:
                await db.execute(
                    f"UPDATE media SET {', '.join(media_fields)} WHERE media_id = ?",
                    (*media_params, video_id),
                )
            await db.commit()
        await _run_with_db_retry(_run)


async def _handle_database_lock_retry(video_id: str, job_id: str | None, stage: str, error: Exception) -> None:
    """Handle transient database lock errors by requeuing the video for another attempt."""
    message = f"Database locked while processing {stage}; requeuing video for another attempt. Details: {str(error)}"
    logger.warning(message)

    await update_video_and_media_state(
        video_id,
        status="QUEUED",
        progress=0.0,
        last_completed_stage=None,
        error_code=None,
        error_message=None,
    )

    if job_id:
        async def _mark_job():
            async for db in get_db():
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED', error_code = 'UNKNOWN_ERROR', error_message = ?
                    WHERE job_id = ?
                    """,
                    (message, job_id),
                )
                await db.commit()
        await _run_with_db_retry(_mark_job)

    # Trigger the next indexing batch in the background so the requeued video is picked up quickly
    asyncio.create_task(start_indexing_queued_videos(limit=1))


@dataclass
class PersonEmbeddingData:
    """Data for a person's learned embeddings."""
    person_id: str
    recognition_mode: str  # 'average', 'reference_only', 'weighted'
    weighted_embedding: np.ndarray | None  # Weighted average of all faces
    reference_embeddings: list[np.ndarray]  # Reference face embeddings
    negative_embeddings: list[np.ndarray]  # Negative example embeddings


async def get_learned_person_embeddings() -> dict[str, PersonEmbeddingData]:
    """
    Get learned embeddings for all known persons with weights.

    Weights:
    - reference faces: 3x weight
    - manual assignments: 2x weight
    - auto assignments: 1x weight
    - legacy assignments: 1x weight

    Returns:
        Dict mapping person_id to PersonEmbeddingData
    """
    person_data: dict[str, dict] = {}

    async for db in get_db():
        # Get recognition mode for all persons
        cursor = await db.execute(
            "SELECT person_id, recognition_mode FROM persons"
        )
        person_rows = await cursor.fetchall()
        for row in person_rows:
            person_data[row["person_id"]] = {
                "recognition_mode": row["recognition_mode"] or "average",
                "embeddings": [],
                "weights": [],
                "reference_embeddings": [],
                "negative_embeddings": [],
            }

        # Get all faces assigned to persons with their assignment sources
        cursor = await db.execute(
            """
            SELECT person_id, embedding, assignment_source
            FROM faces
            WHERE person_id IS NOT NULL
            """
        )
        face_rows = await cursor.fetchall()

        for row in face_rows:
            person_id = row["person_id"]
            if person_id not in person_data:
                continue

            embedding = bytes_to_embedding(row["embedding"])
            source = row["assignment_source"] or "legacy"

            # Assign weight based on source
            if source == "reference":
                weight = 3.0
            elif source == "manual":
                weight = 2.0
            else:  # auto, legacy
                weight = 1.0

            person_data[person_id]["embeddings"].append(embedding)
            person_data[person_id]["weights"].append(weight)

        # Get reference faces (explicitly marked as canonical)
        cursor = await db.execute(
            """
            SELECT fr.person_id, fr.weight, f.embedding
            FROM face_references fr
            JOIN faces f ON fr.face_id = f.face_id
            """
        )
        ref_rows = await cursor.fetchall()

        for row in ref_rows:
            person_id = row["person_id"]
            if person_id in person_data:
                embedding = bytes_to_embedding(row["embedding"])
                person_data[person_id]["reference_embeddings"].append(embedding)

        # Get negative examples
        cursor = await db.execute(
            """
            SELECT fn.person_id, f.embedding
            FROM face_negatives fn
            JOIN faces f ON fn.face_id = f.face_id
            """
        )
        neg_rows = await cursor.fetchall()

        for row in neg_rows:
            person_id = row["person_id"]
            if person_id in person_data:
                embedding = bytes_to_embedding(row["embedding"])
                person_data[person_id]["negative_embeddings"].append(embedding)

    # Compute weighted average embeddings
    result = {}
    for person_id, data in person_data.items():
        weighted_embedding = None
        if data["embeddings"]:
            embeddings = np.array(data["embeddings"])
            weights = np.array(data["weights"])

            # Weighted average
            weighted_sum = np.sum(embeddings * weights[:, np.newaxis], axis=0)
            weighted_embedding = weighted_sum / np.sum(weights)
            # Normalize
            weighted_embedding = weighted_embedding / np.linalg.norm(weighted_embedding)

        result[person_id] = PersonEmbeddingData(
            person_id=person_id,
            recognition_mode=data["recognition_mode"],
            weighted_embedding=weighted_embedding,
            reference_embeddings=data["reference_embeddings"],
            negative_embeddings=data["negative_embeddings"],
        )

    return result


async def get_pair_thresholds() -> dict[tuple[str, str], float]:
    """
    Get pair-specific thresholds for frequently confused person pairs.

    Returns:
        Dict mapping (person_a_id, person_b_id) tuple to threshold
        Keys are sorted so (A, B) and (B, A) both map to the same entry
    """
    thresholds = {}

    async for db in get_db():
        cursor = await db.execute(
            "SELECT person_a_id, person_b_id, threshold FROM person_pair_thresholds"
        )
        rows = await cursor.fetchall()

        for row in rows:
            # Store with sorted key for consistent lookup
            key = tuple(sorted([row["person_a_id"], row["person_b_id"]]))
            thresholds[key] = row["threshold"]

    return thresholds


def find_best_person_match_learned(
    face_embedding: np.ndarray,
    person_embeddings: dict[str, PersonEmbeddingData],
    pair_thresholds: dict[tuple[str, str], float],
    base_threshold: float = 0.65,
) -> tuple[str | None, float, float]:
    """
    Find the best matching person using learned embeddings and pair thresholds.

    Args:
        face_embedding: The face embedding to match
        person_embeddings: Dict of person_id -> PersonEmbeddingData
        pair_thresholds: Dict of (person_a, person_b) -> threshold
        base_threshold: Base minimum similarity threshold

    Returns:
        Tuple of (person_id, similarity, confidence) or (None, 0.0, 0.0) if no match
        Confidence is lowered when match is close to second-best (sibling scenario)
    """
    scores: list[tuple[str, float]] = []

    for person_id, data in person_embeddings.items():
        similarity = 0.0

        if data.recognition_mode == "reference_only":
            # Only compare against reference embeddings
            if data.reference_embeddings:
                ref_similarities = [
                    compute_face_similarity(face_embedding, ref)
                    for ref in data.reference_embeddings
                ]
                similarity = max(ref_similarities)
            else:
                # No references, skip this person
                continue
        elif data.recognition_mode == "weighted":
            # Weighted average with extra reference emphasis
            avg_sim = 0.0
            if data.weighted_embedding is not None:
                avg_sim = compute_face_similarity(face_embedding, data.weighted_embedding)

            ref_sim = 0.0
            if data.reference_embeddings:
                ref_similarities = [
                    compute_face_similarity(face_embedding, ref)
                    for ref in data.reference_embeddings
                ]
                ref_sim = max(ref_similarities)

            # Combine: 60% reference (if available), 40% average
            if data.reference_embeddings:
                similarity = 0.6 * ref_sim + 0.4 * avg_sim
            else:
                similarity = avg_sim
        else:  # 'average' mode (default)
            if data.weighted_embedding is not None:
                similarity = compute_face_similarity(face_embedding, data.weighted_embedding)
            else:
                continue

        # Apply negative penalty
        if data.negative_embeddings:
            neg_similarities = [
                compute_face_similarity(face_embedding, neg)
                for neg in data.negative_embeddings
            ]
            max_neg_similarity = max(neg_similarities)
            # If face is very similar to a negative example, heavily penalize
            if max_neg_similarity > 0.7:
                similarity *= (1.0 - max_neg_similarity)
            elif max_neg_similarity > 0.5:
                similarity *= (1.0 - 0.5 * max_neg_similarity)

        if similarity > 0:
            scores.append((person_id, similarity))

    if not scores:
        return None, 0.0, 0.0

    # Sort by similarity descending
    scores.sort(key=lambda x: x[1], reverse=True)

    best_person, best_similarity = scores[0]

    # Check pair-specific threshold if we have a second candidate
    effective_threshold = base_threshold
    if len(scores) > 1:
        second_person, second_similarity = scores[1]
        pair_key = tuple(sorted([best_person, second_person]))
        if pair_key in pair_thresholds:
            effective_threshold = max(base_threshold, pair_thresholds[pair_key])

    if best_similarity < effective_threshold:
        return None, 0.0, 0.0

    # Calculate confidence based on margin to second best
    confidence = best_similarity
    if len(scores) > 1:
        margin = best_similarity - scores[1][1]
        # Lower confidence when margin is small (ambiguous match)
        if margin < 0.1:
            confidence = best_similarity * (0.7 + 3.0 * margin)  # Scale 0.7-1.0 based on margin

    return best_person, best_similarity, confidence


# Legacy function for backwards compatibility
async def get_known_person_embeddings() -> dict[str, np.ndarray]:
    """
    Get average embeddings for all known persons.

    DEPRECATED: Use get_learned_person_embeddings() for learning-aware matching.

    Returns:
        Dict mapping person_id to average embedding vector
    """
    person_embeddings: dict[str, list[np.ndarray]] = {}

    async for db in get_db():
        # Get all faces that are assigned to a person
        cursor = await db.execute(
            """
            SELECT person_id, embedding
            FROM faces
            WHERE person_id IS NOT NULL
            """
        )
        rows = await cursor.fetchall()

        for row in rows:
            person_id = row["person_id"]
            embedding = bytes_to_embedding(row["embedding"])

            if person_id not in person_embeddings:
                person_embeddings[person_id] = []
            person_embeddings[person_id].append(embedding)

    # Compute average embedding for each person
    result = {}
    for person_id, embeddings in person_embeddings.items():
        if embeddings:
            avg_embedding = np.mean(embeddings, axis=0)
            # Normalize the average
            avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)
            result[person_id] = avg_embedding

    return result


def find_best_person_match(
    face_embedding: np.ndarray,
    person_embeddings: dict[str, np.ndarray],
    threshold: float = 0.65,
) -> tuple[str | None, float]:
    """
    Find the best matching person for a face embedding.

    DEPRECATED: Use find_best_person_match_learned() for learning-aware matching.

    Args:
        face_embedding: The face embedding to match
        person_embeddings: Dict of person_id -> average embedding
        threshold: Minimum similarity threshold (0.65 is conservative for auto-assign)

    Returns:
        Tuple of (person_id, similarity) or (None, 0.0) if no match
    """
    best_person = None
    best_similarity = threshold

    for person_id, person_embedding in person_embeddings.items():
        similarity = compute_face_similarity(face_embedding, person_embedding)
        if similarity > best_similarity:
            best_similarity = similarity
            best_person = person_id

    return best_person, best_similarity


async def process_video(video_id: str) -> None:
    """Process a single video through all indexing stages."""
    logger.info(f"Starting indexing for video {video_id}")

    # Cancel any pending enhanced work for this video
    enhanced_task = _active_enhanced_jobs.pop(video_id, None)
    if enhanced_task:
        enhanced_task.cancel()

    # Get video info
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT video_id, path, filename, library_id, status, last_completed_stage, media_type
            FROM videos
            WHERE video_id = ?
            """,
            (video_id,),
        )
        row = await cursor.fetchone()
        if not row:
            logger.error(f"Video {video_id} not found")
            return

        video_path = Path(row["path"])
        filename = row["filename"]
        current_status = row["status"]
        last_completed_stage = row["last_completed_stage"]
        media_type = row["media_type"] or "video"

    indexer_settings = await get_indexer_settings()
    stages = get_primary_stage_list(
        media_type,
        bool(indexer_settings.get("face_recognition_enabled")),
        str(indexer_settings.get("indexing_preset", "deep")),
    )
    enhanced_stages = get_enhanced_stage_list(
        media_type,
        str(indexer_settings.get("indexing_preset", "deep")),
    )

    # Determine starting stage
    # Verify artifacts exist before resuming from a stage
    start_from = 0
    if last_completed_stage:
        try:
            stage_index = stages.index(last_completed_stage)
            if stages[stage_index] == "EXTRACTING_FRAMES":
                thumbnails_dir = get_thumbnails_dir() / video_id
                has_frames = any(thumbnails_dir.glob("frame_*.jpg"))
                if has_frames:
                    start_from = stage_index + 1 if stage_index < len(stages) - 1 else len(stages)
                else:
                    logger.warning(
                        f"Thumbnails missing, restarting from EXTRACTING_FRAMES: {thumbnails_dir}"
                    )
                    start_from = 0
            else:
                start_from = stage_index + 1 if stage_index < len(stages) - 1 else len(stages)
        except ValueError:
            start_from = 0

    job_id = str(uuid.uuid4())
    created_at_ms = int(datetime.now().timestamp() * 1000)

    # Create job record with retry logic
    async def _create_job():
        async for db in get_db():
            await db.execute(
                """
                INSERT INTO jobs (job_id, video_id, status, created_at_ms, updated_at_ms)
                VALUES (?, ?, 'PENDING', ?, ?)
                """,
                (job_id, video_id, created_at_ms, created_at_ms),
            )
            await db.commit()
    
    await _run_with_db_retry(_create_job)

    try:
        # Update video status to first stage
        current_stage = stages[start_from] if start_from < len(stages) else "DONE"
        await update_video_and_media_state(video_id, status=current_stage)

        # Process through each stage
        for stage_index in range(start_from, len(stages)):
            # Check for cancellation before each stage
            if await check_job_cancelled(video_id):
                logger.info(f"Job cancelled for video {video_id}")
                await emit_job_failed(
                    job_id=job_id,
                    video_id=video_id,
                    stage=current_stage,
                    error_code="CANCELLED",
                    error_message=ERROR_CODES["CANCELLED"],
                )
                return

            stage = stages[stage_index]
            current_stage = stage

            # Update job status with retry logic
            async def _update_job_status():
                async for db in get_db():
                    await db.execute(
                        """
                        UPDATE jobs
                        SET status = ?, current_stage = ?, updated_at_ms = ?
                        WHERE job_id = ?
                        """,
                        (stage, stage, int(datetime.now().timestamp() * 1000), job_id),
                    )
                    await db.commit()
            
            await _run_with_db_retry(_update_job_status)

            # Update video status
            await update_video_and_media_state(
                video_id,
                status=stage,
                last_completed_stage=stage,
            )

            # Emit progress
            progress = (stage_index + 1) / len(stages)
            await emit_job_progress(
                job_id=job_id,
                video_id=video_id,
                stage=stage,
                progress=progress,
                message=f"Processing {stage.replace('_', ' ').lower()}...",
            )

            # Process the stage
            await process_stage(
                video_id,
                video_path,
                stage,
                job_id,
                media_type=media_type,
                frame_interval_seconds=float(indexer_settings.get("frame_interval_seconds", 2.0)),
                thumbnail_quality=int(indexer_settings.get("thumbnail_quality", 85)),
            )

            # Update progress
            await update_video_and_media_state(video_id, progress=progress)

        # Mark as DONE (primary indexing complete)
        indexed_at_ms = int(datetime.now().timestamp() * 1000)
        async def _mark_job_done():
            async for db in get_db():
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = 'DONE', updated_at_ms = ?
                    WHERE job_id = ?
                    """,
                    (indexed_at_ms, job_id),
                )
                await db.commit()
        
        await _run_with_db_retry(_mark_job_done)

        await update_video_and_media_state(video_id, status="DONE", progress=1.0, indexed_at_ms=indexed_at_ms)

        await emit_job_complete(job_id=job_id, video_id=video_id)
        logger.info(f"Completed indexing for video {video_id}")

        if enhanced_stages:
            schedule_enhanced_indexing(video_id, video_path, enhanced_stages)
        
        # Auto-continue: check if we should start more videos
        # Only check if this was the last active job
        active_count = len([t for t in _active_jobs.values() if not t.done()])
        if active_count == 0:
            # Check if there are more queued videos
            queued_count = 0
            async for db in get_db():
                cursor = await db.execute(
                    "SELECT COUNT(*) as count FROM videos WHERE status = 'QUEUED'"
                )
                row = await cursor.fetchone()
                queued_count = row["count"] if row else 0
            
            if queued_count > 0:
                logger.info(f"Auto-continuing indexing: {queued_count} videos queued, starting next batch")
                # Start next batch (non-blocking)
                asyncio.create_task(start_indexing_queued_videos(limit=10))

    except asyncio.CancelledError:
        # Task was cancelled (e.g., by stop_indexing)
        logger.info(f"Indexing task cancelled for video {video_id}")
        await update_video_and_media_state(
            video_id,
            status="CANCELLED",
            error_code="CANCELLED",
            error_message=ERROR_CODES["CANCELLED"],
        )
        async def _cancel_job():
            async for db in get_db():
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = 'CANCELLED', error_code = 'CANCELLED', error_message = ?
                    WHERE job_id = ?
                    """,
                    (ERROR_CODES["CANCELLED"], job_id),
                )
                await db.commit()
        
        await _run_with_db_retry(_cancel_job)

        await emit_job_failed(
            job_id=job_id,
            video_id=video_id,
            stage=current_stage,
            error_code="CANCELLED",
            error_message=ERROR_CODES["CANCELLED"],
        )

    except FileNotFoundError as e:
        logger.error(f"File not found for video {video_id}: {e}")
        error_code = "FILE_NOT_FOUND"
        error_message = ERROR_CODES[error_code]

        await update_video_and_media_state(
            video_id,
            status="FAILED",
            error_code=error_code,
            error_message=error_message,
        )
        async def _mark_job_failed():
            async for db in get_db():
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED', error_code = ?, error_message = ?
                    WHERE job_id = ?
                    """,
                    (error_code, error_message, job_id),
                )
                await db.commit()
        
        await _run_with_db_retry(_mark_job_failed)

        await emit_job_failed(
            job_id=job_id,
            video_id=video_id,
            stage=current_stage,
            error_code=error_code,
            error_message=error_message,
        )

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            await _handle_database_lock_retry(video_id, job_id, current_stage, e)
            return
        raise

    except Exception as e:
        logger.error(f"Indexing failed for video {video_id}: {e}", exc_info=True)

        # Determine error code based on stage and error message
        error_str = str(e).lower()
        if "ffmpeg" in error_str or "ffprobe" in error_str:
            error_code = "FFMPEG_ERROR"
        elif current_stage == "TRANSCRIBING" or "whisper" in error_str:
            error_code = "TRANSCRIPTION_ERROR"
        elif current_stage == "EMBEDDING" or "openclip" in error_str or "clip" in error_str:
            error_code = "EMBEDDING_ERROR"
        elif current_stage == "DETECTING":
            error_code = "DETECTION_ERROR"
        elif current_stage == "DETECTING_FACES" or "insightface" in error_str or "face" in error_str:
            error_code = "FACE_DETECTION_ERROR"
        else:
            error_code = "UNKNOWN_ERROR"

        error_message = f"{ERROR_CODES[error_code]} Details: {str(e)}"

        # Mark as FAILED
        await update_video_and_media_state(
            video_id,
            status="FAILED",
            error_code=error_code,
            error_message=error_message,
        )
        async def _mark_job_failed():
            async for db in get_db():
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED', error_code = ?, error_message = ?
                    WHERE job_id = ?
                    """,
                    (error_code, error_message, job_id),
                )
                await db.commit()
        
        await _run_with_db_retry(_mark_job_failed)

        await emit_job_failed(
            job_id=job_id,
            video_id=video_id,
            stage=current_stage,
            error_code=error_code,
            error_message=error_message,
        )


async def process_stage(
    video_id: str,
    video_path: Path,
    stage: str,
    job_id: str | None = None,
    *,
    media_type: str = "video",
    frame_interval_seconds: float = 2.0,
    thumbnail_quality: int = 85,
) -> None:
    """Process a single indexing stage."""
    logger.debug(f"Processing stage {stage} for video {video_id}")

    if stage == "EXTRACTING_AUDIO":
        # Extract audio using FFmpeg (16kHz mono WAV for Whisper)
        temp_dir = get_temp_dir()
        audio_path = temp_dir / f"{video_id}.wav"
        
        # Check if already exists (resumable)
        # Also verify the file is not empty (might be from a failed extraction)
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            if audio_path.exists() and audio_path.stat().st_size == 0:
                logger.warning(f"Audio file exists but is empty, re-extracting: {audio_path}")
                audio_path.unlink()  # Remove empty file
            
            # Verify video file exists before extraction
            if not video_path.exists():
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            await extract_audio(video_path, audio_path)
            
            # Verify extraction succeeded
            if not audio_path.exists() or audio_path.stat().st_size == 0:
                raise RuntimeError(f"Audio extraction failed: output file missing or empty: {audio_path}")
        else:
            logger.debug(f"Audio already extracted: {audio_path}")
        
        logger.info(f"Audio extraction completed for {video_id}")

    elif stage == "TRANSCRIBING":
        # Transcribe audio using Whisper and save to database
        temp_dir = get_temp_dir()
        audio_path = temp_dir / f"{video_id}.wav"
        
        if not audio_path.exists():
            # Audio file missing - try to re-extract it
            logger.warning(f"Audio file missing for transcription, attempting to re-extract: {audio_path}")
            if not video_path.exists():
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # Re-extract audio
            await extract_audio(video_path, audio_path)
            
            # Verify extraction succeeded
            if not audio_path.exists() or audio_path.stat().st_size == 0:
                raise FileNotFoundError(f"Audio file not found after re-extraction: {audio_path}")

        try:
            # Transcribe
            settings = await get_transcription_settings()
            async def report_progress(progress: float, chunk_index: int, chunk_total: int) -> None:
                if not job_id:
                    return
                await emit_job_progress(
                    job_id=job_id,
                    video_id=video_id,
                    stage=stage,
                    progress=min(max(progress, 0.0), 1.0),
                    message=f"Transcribing chunk {chunk_index}/{chunk_total}",
                )

            segments = await transcribe_audio(
                audio_path,
                model_name=str(settings.get("transcription_model") or "base"),
                language=settings.get("transcription_language") or None,
                backend=str(settings.get("transcription_backend") or "auto"),
                vad_enabled=bool(settings.get("transcription_vad_enabled", True)),
                min_silence_ms=int(settings.get("transcription_min_silence_ms", 500)),
                silence_threshold_db=int(settings.get("transcription_silence_threshold_db", -35)),
                chunk_seconds=float(settings.get("transcription_chunk_seconds", 30.0))
                if settings.get("transcription_chunk_seconds") is not None
                else None,
                on_progress=lambda progress, chunk_index, chunk_total: asyncio.create_task(
                    report_progress(progress, chunk_index, chunk_total)
                ),
            )
            
            # Save to database with retry logic
            async def _save_transcript():
                async for db in get_db():
                    # Clear existing segments for this video
                    await db.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
                    await db.execute("DELETE FROM transcript_fts WHERE video_id = ?", (video_id,))
                    
                    # Insert segments
                    for seg in segments:
                        await db.execute(
                            """
                            INSERT INTO transcript_segments (video_id, start_ms, end_ms, text, confidence)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (video_id, seg["start_ms"], seg["end_ms"], seg["text"], seg.get("confidence")),
                        )
                        
                        # Insert into FTS index
                        await db.execute(
                            """
                            INSERT INTO transcript_fts (video_id, start_ms, end_ms, text)
                            VALUES (?, ?, ?, ?)
                            """,
                            (video_id, seg["start_ms"], seg["end_ms"], seg["text"]),
                        )
                    
                    await db.commit()
            
            await _run_with_db_retry(_save_transcript)
            
            logger.info(f"Transcription completed: {len(segments)} segments for {video_id}")
        except Exception as e:
            if "not installed" in str(e) or "not available" in str(e):
                logger.warning(f"Whisper not available, skipping transcription for {video_id}: {e}")
            else:
                raise

    elif stage == "EXTRACTING_FRAMES":
        thumbnails_dir = get_thumbnails_dir() / video_id
        thumbnails_dir.mkdir(parents=True, exist_ok=True)

        if media_type == "photo":
            frame_path = thumbnails_dir / "frame_000001.jpg"
            if not frame_path.exists():
                create_photo_thumbnail(
                    video_path,
                    frame_path,
                    max_dimension=1280,
                    quality=thumbnail_quality,
                )
            existing_frames = [frame_path]
        else:
            existing_frames = list(thumbnails_dir.glob("frame_*.jpg"))
            # Filter out grid thumbnails from the list
            existing_frames = [f for f in existing_frames if "_grid" not in f.name]
            if not existing_frames:
                await extract_frames(
                    video_path,
                    thumbnails_dir,
                    interval_seconds=frame_interval_seconds,
                )
                existing_frames = sorted(
                    f for f in thumbnails_dir.glob("frame_*.jpg") if "_grid" not in f.name
                )

        # Generate ONE grid thumbnail per media item for fast loading in the media grid
        # Use the first frame for videos, or the photo itself
        # Name it based on the first frame so frontend can find it (e.g., frame_000001_grid.jpg)
        if existing_frames:
            first_frame = existing_frames[0]
            grid_path = first_frame.with_name(first_frame.stem + "_grid.jpg")
            if not grid_path.exists():
                try:
                    create_grid_thumbnail_from_full(
                        first_frame,
                        grid_path,
                        max_dimension=GRID_MAX_DIMENSION,
                        quality=GRID_QUALITY,
                    )
                except Exception as e:
                    logger.warning(f"Failed to create grid thumbnail for {video_id}: {e}")

        # Save frame metadata to database (including colors) with retry logic
        async def _save_frames():
            async for db in get_db():
                # Clear existing frames
                await db.execute("DELETE FROM frames WHERE video_id = ?", (video_id,))

                # Insert frames with color extraction
                for idx, frame_path in enumerate(existing_frames):
                    frame_id = f"{video_id}_frame_{idx:06d}"
                    timestamp_ms = 0 if media_type == "photo" else int(idx * frame_interval_seconds * 1000)

                    try:
                        colors = await extract_dominant_colors(frame_path, num_colors=5)
                        colors_str = ",".join(colors) if colors else None
                    except Exception as e:
                        logger.debug(f"Color extraction failed for frame {idx}: {e}")
                        colors_str = None

                    await db.execute(
                        """
                        INSERT INTO frames (frame_id, video_id, frame_index, timestamp_ms, thumbnail_path, colors)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (frame_id, video_id, idx, timestamp_ms, str(frame_path), colors_str),
                    )

                await db.commit()
        
        await _run_with_db_retry(_save_frames)

        logger.info(f"Frame extraction completed: {len(existing_frames)} frames for {video_id}")

    elif stage == "EMBEDDING":
        # Generate embeddings for frames using OpenCLIP and save to FAISS
        if not _FAISS_AVAILABLE:
            logger.warning("FAISS not available, skipping embeddings")
            return
        
        thumbnails_dir = get_thumbnails_dir() / video_id
        frame_paths = sorted(thumbnails_dir.glob("frame_*.jpg"))
        
        if not frame_paths:
            raise FileNotFoundError(f"No frames found for embedding: {thumbnails_dir}")
        
        try:
            # Generate embeddings
            embeddings_list = []
            for frame_path in frame_paths:
                embedding = await embed_image(frame_path)
                embeddings_list.append(embedding)
            
            if not embeddings_list:
                return
            
            # Convert to numpy array
            embeddings = np.array(embeddings_list, dtype=np.float32)
            
            # Create FAISS index
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatIP(dimension)  # Inner product for normalized embeddings
            
            # Normalize embeddings (OpenCLIP already normalizes, but ensure)
            faiss.normalize_L2(embeddings)
            index.add(embeddings)
            
            # Save index
            faiss_dir = get_faiss_dir()
            faiss_dir.mkdir(parents=True, exist_ok=True)
            index_path = faiss_dir / f"{video_id}.faiss"
            faiss.write_index(index, str(index_path))
            
            logger.info(f"Embedding completed: {len(embeddings_list)} vectors for {video_id}")
        except Exception as e:
            if "not installed" in str(e) or "not available" in str(e):
                logger.warning(f"OpenCLIP not available, skipping embeddings for {video_id}: {e}")
            else:
                raise

    elif stage == "DETECTING":
        # Detect objects in frames using the permissive detector
        thumbnails_dir = get_thumbnails_dir() / video_id
        frame_paths = sorted(thumbnails_dir.glob("frame_*.jpg"))

        if not frame_paths:
            raise FileNotFoundError(f"No frames found for object detection: {thumbnails_dir}")

        try:
            # Get frame IDs from database (single connection)
            frame_ids_by_index = {}
            async for db in get_db():
                cursor = await db.execute(
                    "SELECT frame_id, frame_index FROM frames WHERE video_id = ? ORDER BY frame_index",
                    (video_id,),
                )
                rows = await cursor.fetchall()
                for row in rows:
                    frame_ids_by_index[row["frame_index"]] = row["frame_id"]

            # Detect objects in all frames first (no DB operations)
            all_detections = []
            for idx, frame_path in enumerate(frame_paths):
                frame_id = frame_ids_by_index.get(idx)
                if not frame_id:
                    continue

                detections = await detect_objects(frame_path, confidence_threshold=0.25)
                timestamp_ms = idx * 2000  # 2 seconds per frame

                for det in detections:
                    all_detections.append((
                        video_id, frame_id, timestamp_ms,
                        det["label"], det["confidence"],
                        det.get("bbox_x"), det.get("bbox_y"),
                        det.get("bbox_w"), det.get("bbox_h"),
                    ))

            # Batch write all detections in a single transaction with retry logic
            async def _save_detections():
                async for db in get_db():
                    await db.execute("DELETE FROM detections WHERE video_id = ?", (video_id,))

                    if all_detections:
                        await db.executemany(
                            """
                            INSERT INTO detections (
                                video_id, frame_id, timestamp_ms, label, confidence,
                                bbox_x, bbox_y, bbox_w, bbox_h
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            all_detections,
                        )

                    await db.commit()
            
            await _run_with_db_retry(_save_detections)

            logger.info(f"Object detection completed: {len(all_detections)} detections for {video_id}")
        except Exception as e:
            if "not installed" in str(e) or "not available" in str(e):
                logger.warning(f"Detector not available, skipping object detection for {video_id}: {e}")
            else:
                raise

    elif stage == "DETECTING_FACES":
        # Detect faces in frames and extract embeddings
        thumbnails_dir = get_thumbnails_dir() / video_id
        frame_paths = sorted(thumbnails_dir.glob("frame_*.jpg"))

        if not frame_paths:
            raise FileNotFoundError(f"No frames found for face detection: {thumbnails_dir}")

        try:
            # Load learned person embeddings for auto-recognition
            learned_persons = await get_learned_person_embeddings()
            pair_thresholds = await get_pair_thresholds()
            logger.debug(f"Loaded {len(learned_persons)} known persons for auto-recognition")

            # Get frame IDs from database (single connection)
            frame_ids_by_index = {}
            async for db in get_db():
                cursor = await db.execute(
                    "SELECT frame_id, frame_index, timestamp_ms FROM frames WHERE video_id = ? ORDER BY frame_index",
                    (video_id,),
                )
                rows = await cursor.fetchall()
                for row in rows:
                    frame_ids_by_index[row["frame_index"]] = {
                        "frame_id": row["frame_id"],
                        "timestamp_ms": row["timestamp_ms"],
                    }

            # Detect faces in all frames first (file operations, no DB)
            faces_dir = get_faces_dir() / video_id
            faces_dir.mkdir(parents=True, exist_ok=True)

            all_faces_data = []
            auto_recognized = 0
            created_at_ms = int(datetime.now().timestamp() * 1000)

            for idx, frame_path in enumerate(frame_paths):
                frame_info = frame_ids_by_index.get(idx)
                if not frame_info:
                    continue

                frame_id = frame_info["frame_id"]
                timestamp_ms = frame_info["timestamp_ms"]

                # Detect faces with embeddings
                faces = await detect_faces(frame_path, det_thresh=0.5)

                for face_idx, face in enumerate(faces):
                    face_id = f"{video_id}_face_{idx:06d}_{face_idx:02d}"

                    # Extract face crop (file I/O, not DB)
                    crop_path = faces_dir / f"{face_id}.jpg"
                    await extract_face_crop(
                        frame_path,
                        (face["bbox_x"], face["bbox_y"], face["bbox_w"], face["bbox_h"]),
                        crop_path,
                    )

                    # Convert embedding to bytes for storage
                    embedding_bytes = embedding_to_bytes(face["embedding"])

                    # Auto-recognition: try to match against known persons using learned matching
                    matched_person_id = None
                    assignment_confidence = None
                    assignment_source = None
                    assigned_at_ms = None

                    if learned_persons:
                        matched_person_id, similarity, confidence = find_best_person_match_learned(
                            face["embedding"],
                            learned_persons,
                            pair_thresholds,
                            base_threshold=0.65,  # Conservative threshold for auto-assign
                        )
                        if matched_person_id:
                            auto_recognized += 1
                            assignment_confidence = confidence
                            assignment_source = "auto"
                            assigned_at_ms = created_at_ms
                            logger.debug(
                                f"Auto-recognized face {face_id} as person {matched_person_id} "
                                f"(similarity: {similarity:.3f}, confidence: {confidence:.3f})"
                            )

                    all_faces_data.append((
                        face_id, video_id, frame_id, timestamp_ms,
                        face["bbox_x"], face["bbox_y"], face["bbox_w"], face["bbox_h"],
                        face["confidence"], embedding_bytes, str(crop_path),
                        face.get("age"), face.get("gender"), matched_person_id,
                        assignment_source, assignment_confidence, assigned_at_ms,
                        created_at_ms,
                    ))

            # Batch write all faces in a single transaction with retry logic
            async def _save_faces():
                async for db in get_db():
                    await db.execute("DELETE FROM faces WHERE video_id = ?", (video_id,))

                    if all_faces_data:
                        await db.executemany(
                            """
                            INSERT INTO faces (
                                face_id, video_id, frame_id, timestamp_ms,
                                bbox_x, bbox_y, bbox_w, bbox_h, confidence,
                                embedding, crop_path, age, gender, person_id,
                                assignment_source, assignment_confidence, assigned_at_ms,
                                created_at_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            all_faces_data,
                        )

                    # Update face counts for any auto-recognized persons
                    if auto_recognized > 0:
                        await db.execute(
                            """
                            UPDATE persons
                            SET face_count = (SELECT COUNT(*) FROM faces WHERE faces.person_id = persons.person_id),
                                updated_at_ms = ?
                            WHERE person_id IN (SELECT DISTINCT person_id FROM faces WHERE video_id = ? AND person_id IS NOT NULL)
                            """,
                            (created_at_ms, video_id),
                        )

                    await db.commit()

            await _run_with_db_retry(_save_faces)

            logger.info(
                f"Face detection completed: {len(all_faces_data)} faces for {video_id} "
                f"({auto_recognized} auto-recognized)"
            )
        except Exception as e:
            if "not installed" in str(e) or "not available" in str(e):
                logger.warning(f"Face detector not available, skipping face detection for {video_id}: {e}")
            else:
                raise

    else:
        raise ValueError(f"Unknown stage: {stage}")


async def start_indexing_queued_videos(limit: int = 10) -> dict:
    """Start indexing for up to N queued videos."""
    global _indexing_paused
    
    # Check if indexing is paused
    if _indexing_paused:
        return {"started": 0, "message": "Indexing is paused"}
    
    settings = await get_indexer_settings()
    max_jobs = int(settings.get("max_concurrent_jobs", 2))
    active_count = len([t for t in _active_jobs.values() if not t.done()])
    available_slots = max(max_jobs - active_count, 0)
    if available_slots <= 0:
        return {"started": 0, "message": "Max concurrent jobs already running"}

    # Cap at 1 to avoid SQLite "database is locked" (multiple indexers writing concurrently)
    limit = min(limit, available_slots, 1)
    logger.info(f"Starting indexing for up to {limit} queued videos")

    # Get queued videos
    # Check if we should prioritize recent media
    settings = await get_indexer_settings()
    prioritize_recent = settings.get("prioritize_recent_media", False)
    
    video_ids: list[str] = []
    async for db in get_db():
        if prioritize_recent:
            # Order by mtime_ms DESC (most recently modified first)
            # Fallback to creation_time if mtime not available
            cursor = await db.execute(
                """
                SELECT video_id FROM videos
                WHERE status = 'QUEUED'
                ORDER BY 
                    CASE 
                        WHEN mtime_ms IS NOT NULL AND mtime_ms > 0 THEN mtime_ms
                        WHEN creation_time IS NOT NULL THEN CAST(creation_time AS INTEGER)
                        ELSE created_at_ms
                    END DESC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            # Default: oldest first (FIFO)
            cursor = await db.execute(
                """
                SELECT video_id FROM videos
                WHERE status = 'QUEUED'
                ORDER BY created_at_ms ASC
                LIMIT ?
                """,
                (limit,),
            )
        rows = await cursor.fetchall()
        video_ids = [row["video_id"] for row in rows]

    if not video_ids:
        return {"started": 0, "message": "No queued videos found"}

    # Start processing tasks (one at a time for now)
    started = 0
    for video_id in video_ids:
        if video_id not in _active_jobs:
            task = asyncio.create_task(process_video(video_id))
            _active_jobs[video_id] = task
            started += 1
            # Clean up completed tasks from the active jobs dict
            def make_cleanup(vid: str):
                def cleanup(t):
                    _active_jobs.pop(vid, None)
                return cleanup
            task.add_done_callback(make_cleanup(video_id))

    return {"started": started, "video_ids": video_ids}


async def auto_continue_indexing() -> None:
    """Auto-continue indexing when videos complete."""
    global _indexing_paused
    
    while True:
        await asyncio.sleep(5)  # Check every 5 seconds
        
        # Skip if paused
        if _indexing_paused:
            continue
        
        # Count active jobs
        active_count = len([t for t in _active_jobs.values() if not t.done()])
        
        # Get queued videos count
        queued_count = 0
        async for db in get_db():
            cursor = await db.execute(
                "SELECT COUNT(*) as count FROM videos WHERE status = 'QUEUED'"
            )
            row = await cursor.fetchone()
            queued_count = row["count"] if row else 0
        
        # If we have queued videos but no active jobs, start more
        if queued_count > 0 and active_count == 0:
            logger.info(f"Auto-continuing indexing: {queued_count} videos queued, 0 active")
            await start_indexing_queued_videos(limit=10)


def pause_indexing() -> None:
    """Pause indexing (stops starting new jobs, but doesn't cancel running ones)."""
    global _indexing_paused
    _indexing_paused = True
    logger.info("Indexing paused by user")


def resume_indexing() -> None:
    """Resume indexing."""
    global _indexing_paused
    _indexing_paused = False
    logger.info("Indexing resumed by user")


def is_indexing_paused() -> bool:
    """Check if indexing is paused."""
    return _indexing_paused


async def stop_indexing(video_id: Optional[str] = None) -> dict:
    """Stop indexing for a specific video or all videos."""
    if video_id:
        stopped: list[str] = []
        if video_id in _active_jobs:
            _active_jobs[video_id].cancel()
            del _active_jobs[video_id]
            stopped.append(video_id)
        if video_id in _active_enhanced_jobs:
            _active_enhanced_jobs[video_id].cancel()
            del _active_enhanced_jobs[video_id]
            if video_id not in stopped:
                stopped.append(video_id)
        return {"stopped": stopped}
    else:
        # Cancel all
        for task in _active_jobs.values():
            task.cancel()
        stopped = list(_active_jobs.keys())
        _active_jobs.clear()
        for task in _active_enhanced_jobs.values():
            task.cancel()
        stopped.extend(list(_active_enhanced_jobs.keys()))
        _active_enhanced_jobs.clear()
        return {"stopped": stopped}


async def _run_enhanced_indexing(
    video_id: str,
    video_path: Path,
    stages: list[str],
) -> None:
    """Run enhanced indexing stages quietly in the background."""
    try:
        # Look up actual media type from database
        media_type = "video"  # default
        async for db in get_db():
            cursor = await db.execute(
                "SELECT media_type FROM videos WHERE video_id = ?",
                (video_id,),
            )
            row = await cursor.fetchone()
            if row:
                media_type = row["media_type"]
        
        # Filter stages based on media type
        # Skip audio/transcription stages for photos
        audio_stages = {"EXTRACTING_AUDIO", "TRANSCRIBING"}
        filtered_stages = stages
        if media_type != "video":
            filtered_stages = [s for s in stages if s not in audio_stages]
            if len(filtered_stages) < len(stages):
                logger.debug(f"Skipping audio stages for {media_type} {video_id}")
        
        for stage in filtered_stages:
            await process_stage(
                video_id,
                video_path,
                stage,
                job_id=None,
                media_type=media_type,
            )
    except asyncio.CancelledError:
        logger.info(f"Enhanced indexing cancelled for video {video_id}")
    except Exception as e:
        logger.warning(f"Enhanced indexing failed for video {video_id}: {e}")


def schedule_enhanced_indexing(video_id: str, video_path: Path, stages: list[str]) -> None:
    """Schedule enhanced indexing without blocking primary indexing."""
    if not stages:
        return
    if video_id in _active_enhanced_jobs:
        return
    task = asyncio.create_task(_run_enhanced_indexing(video_id, video_path, stages))
    _active_enhanced_jobs[video_id] = task

    def cleanup(t: asyncio.Task) -> None:
        _active_enhanced_jobs.pop(video_id, None)

    task.add_done_callback(cleanup)


async def regenerate_grid_thumbnails() -> dict:
    """
    Regenerate grid thumbnails for all existing indexed media.

    Creates small, fast-loading thumbnails (256px, 50% quality) for media
    that doesn't already have grid thumbnails. One thumbnail per media item.
    """
    thumbnails_dir = get_thumbnails_dir()
    generated = 0
    skipped = 0
    errors = 0

    logger.info("Starting grid thumbnail regeneration")

    # Find all video/media directories in thumbnails folder
    for video_dir in thumbnails_dir.iterdir():
        if not video_dir.is_dir():
            continue

        # Find the first frame (excluding existing grid thumbnails)
        frames = sorted(
            f for f in video_dir.glob("frame_*.jpg") 
            if "_grid" not in f.name
        )

        if not frames:
            skipped += 1
            continue

        # Use the first frame to create the grid thumbnail
        # Name it based on the first frame so frontend can find it (e.g., frame_000001_grid.jpg)
        first_frame = frames[0]
        grid_path = first_frame.with_name(first_frame.stem + "_grid.jpg")

        # Skip if grid thumbnail already exists
        if grid_path.exists():
            skipped += 1
            continue

        try:
            create_grid_thumbnail_from_full(
                first_frame,
                grid_path,
                max_dimension=GRID_MAX_DIMENSION,
                quality=GRID_QUALITY,
            )
            generated += 1

            # Log progress periodically
            if generated % 10 == 0:
                logger.info(f"Grid thumbnails: {generated} generated, {skipped} skipped")

        except Exception as e:
            logger.warning(f"Failed to create grid thumbnail for {first_frame}: {e}")
            errors += 1

    logger.info(
        f"Grid thumbnail regeneration complete: {generated} generated, "
        f"{skipped} skipped, {errors} errors"
    )

    return {"generated": generated, "skipped": skipped, "errors": errors}


async def upgrade_to_deep_indexing(library_id: str | None = None) -> dict:
    """
    Upgrade already-indexed videos from quick to deep mode.

    Runs enhanced stages (object detection, face detection, transcription)
    on videos that were previously indexed with 'quick' preset.
    """
    upgraded = 0
    skipped = 0

    indexer_settings = await get_indexer_settings()
    face_recognition_enabled = bool(indexer_settings.get("face_recognition_enabled", False))

    async for db in get_db():

        # Find videos that are DONE but may not have enhanced stages completed
        query = """
            SELECT v.video_id, v.path, v.last_completed_stage, v.media_type
            FROM videos v
            WHERE v.status = 'DONE'
        """
        params: list[object] = []

        if library_id:
            query += " AND v.library_id = ?"
            params.append(library_id)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        for row in rows:
            video_id = row["video_id"]
            video_path = Path(row["path"])
            last_stage = row["last_completed_stage"]
            media_type = row["media_type"] or "video"

            # Check if video file still exists
            if not video_path.exists():
                skipped += 1
                continue

            # Determine which stages need to be run
            stages_to_run: list[str] = []

            # Check if detection was done (for quick->deep upgrade)
            if last_stage not in ["DETECTING", "DETECTING_FACES", "TRANSCRIBING"]:
                stages_to_run.append("DETECTING")
                if face_recognition_enabled:
                    stages_to_run.append("DETECTING_FACES")
            elif last_stage == "DETECTING" and face_recognition_enabled:
                stages_to_run.append("DETECTING_FACES")

            # Only run audio/transcription on videos
            if media_type == "video":
                stages_to_run.extend(VIDEO_ENHANCED_STAGES)

            if stages_to_run:
                schedule_enhanced_indexing(video_id, video_path, stages_to_run)
                upgraded += 1
            else:
                skipped += 1

    logger.info(f"Deep upgrade started: {upgraded} videos queued, {skipped} skipped")
    return {"upgraded": upgraded, "skipped": skipped}
