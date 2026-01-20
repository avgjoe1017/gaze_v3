"""Video indexing pipeline."""

import asyncio
import json
import uuid
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
from ..utils.logging import get_logger
from ..utils.paths import get_temp_dir, get_thumbnails_dir, get_faiss_dir
from ..ws.handler import emit_job_progress, emit_job_complete, emit_job_failed

logger = get_logger(__name__)

# Stage order for state machine
STAGES = [
    "EXTRACTING_AUDIO",
    "TRANSCRIBING",
    "EXTRACTING_FRAMES",
    "EMBEDDING",
    "DETECTING",
    "DETECTING_FACES",
]

# Track active indexing jobs
_active_jobs: dict[str, asyncio.Task] = {}

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


async def get_known_person_embeddings() -> dict[str, np.ndarray]:
    """
    Get average embeddings for all known persons.

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

    # Get video info
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT video_id, path, filename, library_id, status, last_completed_stage
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

    # Determine starting stage
    # Verify artifacts exist before resuming from a stage
    start_from = 0
    if last_completed_stage:
        try:
            stage_index = STAGES.index(last_completed_stage)
            # Check if we can resume from the next stage
            # Verify required artifacts exist for the completed stage
            temp_dir = get_temp_dir()
            
            if last_completed_stage == "EXTRACTING_AUDIO":
                # Verify audio file exists and is not empty
                audio_path = temp_dir / f"{video_id}.wav"
                if audio_path.exists() and audio_path.stat().st_size > 0:
                    start_from = stage_index + 1
                else:
                    logger.warning(f"Audio file missing or empty, restarting from EXTRACTING_AUDIO: {audio_path}")
                    start_from = 0
            elif stage_index < len(STAGES) - 1:
                # For other stages, check if audio exists (required for all subsequent stages)
                audio_path = temp_dir / f"{video_id}.wav"
                if audio_path.exists() and audio_path.stat().st_size > 0:
                    start_from = stage_index + 1
                else:
                    logger.warning(f"Audio file missing, restarting from EXTRACTING_AUDIO: {audio_path}")
                    start_from = 0
            else:
                start_from = len(STAGES)
        except ValueError:
            start_from = 0

    job_id = str(uuid.uuid4())
    created_at_ms = int(datetime.now().timestamp() * 1000)

    # Create job record
    async for db in get_db():
        await db.execute(
            """
            INSERT INTO jobs (job_id, video_id, status, created_at_ms, updated_at_ms)
            VALUES (?, ?, 'PENDING', ?, ?)
            """,
            (job_id, video_id, created_at_ms, created_at_ms),
        )
        await db.commit()

    try:
        # Update video status to first stage
        current_stage = STAGES[start_from] if start_from < len(STAGES) else "DONE"
        async for db in get_db():
            await db.execute(
                "UPDATE videos SET status = ? WHERE video_id = ?",
                (current_stage, video_id),
            )
            await db.commit()

        # Process through each stage
        for stage_index in range(start_from, len(STAGES)):
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

            stage = STAGES[stage_index]
            current_stage = stage

            # Update job status
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

            # Update video status
            async for db in get_db():
                await db.execute(
                    "UPDATE videos SET status = ?, last_completed_stage = ? WHERE video_id = ?",
                    (stage, stage, video_id),
                )
                await db.commit()

            # Emit progress
            progress = (stage_index + 1) / len(STAGES)
            await emit_job_progress(
                job_id=job_id,
                video_id=video_id,
                stage=stage,
                progress=progress,
                message=f"Processing {stage.replace('_', ' ').lower()}...",
            )

            # Process the stage
            await process_stage(video_id, video_path, stage, job_id)

            # Update progress
            async for db in get_db():
                await db.execute(
                    "UPDATE videos SET progress = ? WHERE video_id = ?",
                    (progress, video_id),
                )
                await db.commit()

        # Mark as DONE
        indexed_at_ms = int(datetime.now().timestamp() * 1000)
        async for db in get_db():
            await db.execute(
                """
                UPDATE videos
                SET status = 'DONE', progress = 1.0, indexed_at_ms = ?
                WHERE video_id = ?
                """,
                (indexed_at_ms, video_id),
            )
            await db.execute(
                """
                UPDATE jobs
                SET status = 'DONE', updated_at_ms = ?
                WHERE job_id = ?
                """,
                (indexed_at_ms, job_id),
            )
            await db.commit()

        await emit_job_complete(job_id=job_id, video_id=video_id)
        logger.info(f"Completed indexing for video {video_id}")
        
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
        async for db in get_db():
            await db.execute(
                """
                UPDATE videos
                SET status = 'CANCELLED', error_code = 'CANCELLED', error_message = ?
                WHERE video_id = ?
                """,
                (ERROR_CODES["CANCELLED"], video_id),
            )
            await db.execute(
                """
                UPDATE jobs
                SET status = 'CANCELLED', error_code = 'CANCELLED', error_message = ?
                WHERE job_id = ?
                """,
                (ERROR_CODES["CANCELLED"], job_id),
            )
            await db.commit()

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

        async for db in get_db():
            await db.execute(
                """
                UPDATE videos
                SET status = 'FAILED', error_code = ?, error_message = ?
                WHERE video_id = ?
                """,
                (error_code, error_message, video_id),
            )
            await db.execute(
                """
                UPDATE jobs
                SET status = 'FAILED', error_code = ?, error_message = ?
                WHERE job_id = ?
                """,
                (error_code, error_message, job_id),
            )
            await db.commit()

        await emit_job_failed(
            job_id=job_id,
            video_id=video_id,
            stage=current_stage,
            error_code=error_code,
            error_message=error_message,
        )

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
        async for db in get_db():
            await db.execute(
                """
                UPDATE videos
                SET status = 'FAILED', error_code = ?, error_message = ?
                WHERE video_id = ?
                """,
                (error_code, error_message, video_id),
            )
            await db.execute(
                """
                UPDATE jobs
                SET status = 'FAILED', error_code = ?, error_message = ?
                WHERE job_id = ?
                """,
                (error_code, error_message, job_id),
            )
            await db.commit()

        await emit_job_failed(
            job_id=job_id,
            video_id=video_id,
            stage=current_stage,
            error_code=error_code,
            error_message=error_message,
        )


async def process_stage(video_id: str, video_path: Path, stage: str, job_id: str | None = None) -> None:
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
            
            # Save to database
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
            
            logger.info(f"Transcription completed: {len(segments)} segments for {video_id}")
        except Exception as e:
            if "not installed" in str(e) or "not available" in str(e):
                logger.warning(f"Whisper not available, skipping transcription for {video_id}: {e}")
            else:
                raise

    elif stage == "EXTRACTING_FRAMES":
        # Extract frames using FFmpeg (1 frame per 2 seconds)
        thumbnails_dir = get_thumbnails_dir() / video_id
        thumbnails_dir.mkdir(parents=True, exist_ok=True)

        # Check if frames already exist (resumable)
        existing_frames = list(thumbnails_dir.glob("frame_*.jpg"))
        if not existing_frames:
            await extract_frames(video_path, thumbnails_dir, interval_seconds=2.0)
            existing_frames = sorted(thumbnails_dir.glob("frame_*.jpg"))

        # Save frame metadata to database (including colors)
        async for db in get_db():
            # Clear existing frames
            await db.execute("DELETE FROM frames WHERE video_id = ?", (video_id,))

            # Insert frames with color extraction
            for idx, frame_path in enumerate(existing_frames):
                frame_id = f"{video_id}_frame_{idx:06d}"
                # Calculate timestamp from frame index (2 seconds per frame)
                timestamp_ms = idx * 2000

                # Extract dominant colors for this frame
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

            # Batch write all detections in a single transaction
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
            # Load known person embeddings for auto-recognition
            known_persons = await get_known_person_embeddings()
            logger.debug(f"Loaded {len(known_persons)} known persons for auto-recognition")

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

                    # Auto-recognition: try to match against known persons
                    matched_person_id = None
                    if known_persons:
                        matched_person_id, similarity = find_best_person_match(
                            face["embedding"],
                            known_persons,
                            threshold=0.65,  # Conservative threshold for auto-assign
                        )
                        if matched_person_id:
                            auto_recognized += 1
                            logger.debug(
                                f"Auto-recognized face {face_id} as person {matched_person_id} "
                                f"(similarity: {similarity:.3f})"
                            )

                    all_faces_data.append((
                        face_id, video_id, frame_id, timestamp_ms,
                        face["bbox_x"], face["bbox_y"], face["bbox_w"], face["bbox_h"],
                        face["confidence"], embedding_bytes, str(crop_path),
                        face.get("age"), face.get("gender"), matched_person_id, created_at_ms,
                    ))

            # Batch write all faces in a single transaction
            async for db in get_db():
                await db.execute("DELETE FROM faces WHERE video_id = ?", (video_id,))

                if all_faces_data:
                    await db.executemany(
                        """
                        INSERT INTO faces (
                            face_id, video_id, frame_id, timestamp_ms,
                            bbox_x, bbox_y, bbox_w, bbox_h, confidence,
                            embedding, crop_path, age, gender, person_id, created_at_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    logger.info(f"Starting indexing for up to {limit} queued videos")

    # Get queued videos
    video_ids: list[str] = []
    async for db in get_db():
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
    while True:
        await asyncio.sleep(5)  # Check every 5 seconds
        
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


async def stop_indexing(video_id: Optional[str] = None) -> dict:
    """Stop indexing for a specific video or all videos."""
    if video_id:
        if video_id in _active_jobs:
            _active_jobs[video_id].cancel()
            del _active_jobs[video_id]
            return {"stopped": [video_id]}
        return {"stopped": []}
    else:
        # Cancel all
        for task in _active_jobs.values():
            task.cancel()
        stopped = list(_active_jobs.keys())
        _active_jobs.clear()
        return {"stopped": stopped}
