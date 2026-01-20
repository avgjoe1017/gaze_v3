"""Whisper transcription wrapper."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from threading import Lock
from typing import Optional, Callable

from ..utils.ffmpeg import detect_nonsilent_segments, extract_audio_segment, get_wav_duration_seconds
from ..utils.logging import get_logger
from ..utils.paths import get_models_dir, get_temp_dir

logger = get_logger(__name__)

# Check if whisper is available
try:
    import whisper

    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False
    logger.warning("Whisper not available. Install with: pip install openai-whisper")

# Optional faster-whisper backend
try:
    from faster_whisper import WhisperModel
    import ctranslate2

    _FAST_WHISPER_AVAILABLE = True
except ImportError:
    _FAST_WHISPER_AVAILABLE = False

# Optional Silero VAD
try:
    import torch
    from silero_vad import load_silero_vad, get_speech_timestamps

    _SILERO_AVAILABLE = True
except ImportError:
    _SILERO_AVAILABLE = False

_model_lock = Lock()
_inference_lock = Lock()
_openai_model_cache: dict[str, object] = {}
_faster_model_cache: dict[str, object] = {}
_silero_model: object | None = None


def _load_openai_model(model_name: str) -> object:
    """Load and cache OpenAI Whisper model."""
    if not _WHISPER_AVAILABLE:
        raise RuntimeError("Whisper is not installed. Install with: pip install openai-whisper")

    with _model_lock:
        if model_name in _openai_model_cache:
            return _openai_model_cache[model_name]

        models_dir = get_models_dir()
        model_path = models_dir / "whisper-base.pt"

        device = "cpu"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
        except Exception:
            device = "cpu"

        if model_name == "base" and model_path.exists():
            logger.debug(f"Loading Whisper model from {model_path}")
            model = whisper.load_model(str(model_path), device=device)
        else:
            model = whisper.load_model(model_name, device=device)

        _openai_model_cache[model_name] = model
        return model


def _load_faster_model(model_name: str) -> WhisperModel:
    """Load and cache faster-whisper model."""
    if not _FAST_WHISPER_AVAILABLE:
        raise RuntimeError("faster-whisper is not installed. Install with: pip install faster-whisper")

    with _model_lock:
        if model_name in _faster_model_cache:
            return _faster_model_cache[model_name]  # type: ignore[return-value]

        device = os.environ.get("GAZE_WHISPER_DEVICE")
        if not device:
            try:
                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _faster_model_cache[model_name] = model
        return model


def _load_silero_model() -> object:
    global _silero_model
    if not _SILERO_AVAILABLE:
        raise RuntimeError("silero-vad is not installed. Install with: pip install silero-vad")

    if _silero_model is None:
        _silero_model = load_silero_vad()
    return _silero_model


def _silero_vad_segments(
    audio_path: Path,
    sample_rate: int = 16000,
) -> list[tuple[float, float]]:
    if not _SILERO_AVAILABLE:
        return []

    import wave

    with wave.open(str(audio_path), "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
        audio = torch.frombuffer(frames, dtype=torch.int16).float() / 32768.0

    model = _load_silero_model()
    timestamps = get_speech_timestamps(audio, model, sampling_rate=sample_rate)

    segments = []
    for ts in timestamps:
        start = ts["start"] / sample_rate
        end = ts["end"] / sample_rate
        if end > start:
            segments.append((start, end))
    return segments


def _chunk_segments(
    segments: list[tuple[float, float]],
    chunk_seconds: float | None,
) -> list[tuple[float, float]]:
    if not segments or not chunk_seconds or chunk_seconds <= 0:
        return segments

    chunked: list[tuple[float, float]] = []
    for start, end in segments:
        current = start
        while current < end:
            next_end = min(end, current + chunk_seconds)
            if next_end - current >= 0.2:
                chunked.append((current, next_end))
            current = next_end
    return chunked


def _build_segments(
    audio_path: Path,
    vad_enabled: bool,
    min_silence_ms: int,
    silence_threshold_db: int,
    chunk_seconds: float | None,
) -> list[tuple[float, float]]:
    duration = get_wav_duration_seconds(audio_path)
    if duration is None:
        logger.warning(f"Failed to read WAV duration for {audio_path}")
        return []
    if duration <= 0:
        logger.warning(f"WAV duration is zero for {audio_path}")
        return []

    logger.debug(
        "Building segments for %s: duration=%.2fs, vad=%s, min_silence_ms=%s, "
        "silence_threshold_db=%s, chunk_seconds=%s",
        audio_path,
        duration,
        vad_enabled,
        min_silence_ms,
        silence_threshold_db,
        chunk_seconds,
    )

    if vad_enabled:
        segments: list[tuple[float, float]] = []
        # Prefer Silero VAD if available, else fall back to ffmpeg silencedetect
        if _SILERO_AVAILABLE:
            try:
                segments = _silero_vad_segments(audio_path)
            except Exception as e:
                logger.debug(f"Silero VAD failed, falling back to ffmpeg: {e}")
                segments = []

        if not segments:
            segments = detect_nonsilent_segments(
                audio_path,
                min_silence_ms=min_silence_ms,
                silence_threshold_db=silence_threshold_db,
            )
        if not segments:
            segments = [(0.0, duration)]
    else:
        segments = [(0.0, duration)]

    segments = _chunk_segments(segments, chunk_seconds)
    if not segments:
        logger.warning(f"No segments built for {audio_path} (duration={duration:.2f}s)")
    else:
        logger.debug(
            "Built %d segments for %s (first=%.2f-%.2fs, last=%.2f-%.2fs)",
            len(segments),
            audio_path,
            segments[0][0],
            segments[0][1],
            segments[-1][0],
            segments[-1][1],
        )
    return segments


def _transcribe_with_openai(
    audio_path: Path,
    model_name: str,
    language: Optional[str],
    vad_enabled: bool,
    min_silence_ms: int,
    silence_threshold_db: int,
    chunk_seconds: float | None,
    progress_cb: Optional[callable] = None,
) -> list[dict]:
    model = _load_openai_model(model_name)

    segments = _build_segments(
        audio_path,
        vad_enabled=vad_enabled,
        min_silence_ms=min_silence_ms,
        silence_threshold_db=silence_threshold_db,
        chunk_seconds=chunk_seconds,
    )

    if not segments:
        # Fallback: transcribe full file
        with _inference_lock:
            result = model.transcribe(
                str(audio_path),
                language=language,
                word_timestamps=False,
                verbose=False,
            )
        return [
            {
                "start_ms": int(seg["start"] * 1000),
                "end_ms": int(seg["end"] * 1000),
                "text": seg["text"].strip(),
                "confidence": seg.get("no_speech_prob", 1.0 - seg.get("avg_logprob", 0.0)),
            }
            for seg in result.get("segments", [])
        ]

    temp_dir = get_temp_dir()
    output_segments: list[dict] = []

    total_duration = get_wav_duration_seconds(audio_path) or 0.0
    processed = 0.0

    for idx, (start, end) in enumerate(segments):
        segment_duration = end - start
        
        # Skip segments that are too short (Whisper needs at least ~0.5 seconds)
        if segment_duration < 0.5:
            logger.debug(f"Skipping segment {idx}: too short ({segment_duration:.2f}s)")
            processed += segment_duration
            if progress_cb and total_duration > 0:
                progress_cb(processed / total_duration, idx + 1, len(segments))
            continue
        
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, dir=temp_dir
        ) as tmp_file:
            segment_path = Path(tmp_file.name)

        try:
            extract_audio_segment(audio_path, segment_path, start, end)
            
            # Verify segment file was created and has content
            if not segment_path.exists():
                logger.warning(f"Segment file not created: {segment_path}")
                processed += segment_duration
                if progress_cb and total_duration > 0:
                    progress_cb(processed / total_duration, idx + 1, len(segments))
                continue
            
            file_size = segment_path.stat().st_size
            if file_size < 1000:  # Less than 1KB is likely empty/corrupted
                logger.warning(f"Segment file too small ({file_size} bytes), skipping: {segment_path}")
                processed += segment_duration
                if progress_cb and total_duration > 0:
                    progress_cb(processed / total_duration, idx + 1, len(segments))
                continue

            segment_wav_duration = get_wav_duration_seconds(segment_path)
            if segment_wav_duration is None or segment_wav_duration < 0.5:
                logger.warning(
                    "Segment WAV too short after extraction (idx=%d, range=%.2f-%.2fs, "
                    "size=%d bytes, wav_duration=%s) -> skipping",
                    idx,
                    start,
                    end,
                    file_size,
                    f"{segment_wav_duration:.3f}s" if segment_wav_duration is not None else "unknown",
                )
                processed += segment_duration
                if progress_cb and total_duration > 0:
                    progress_cb(processed / total_duration, idx + 1, len(segments))
                continue

            logger.debug(
                "Segment WAV ok (idx=%d, range=%.2f-%.2fs, size=%d bytes, wav_duration=%.3fs)",
                idx,
                start,
                end,
                file_size,
                segment_wav_duration,
            )
            
            with _inference_lock:
                result = model.transcribe(
                    str(segment_path),
                    language=language,
                    word_timestamps=False,
                    verbose=False,
                )
            for seg in result.get("segments", []):
                output_segments.append(
                    {
                        "start_ms": int((seg["start"] + start) * 1000),
                        "end_ms": int((seg["end"] + start) * 1000),
                        "text": seg["text"].strip(),
                        "confidence": seg.get("no_speech_prob", 1.0 - seg.get("avg_logprob", 0.0)),
                    }
                )
            processed += segment_duration
            if progress_cb and total_duration > 0:
                progress_cb(processed / total_duration, idx + 1, len(segments))
        except Exception as e:
            logger.warning(f"Failed to transcribe segment {idx} ({start:.2f}-{end:.2f}s): {e}")
            # Continue with next segment instead of failing entire transcription
            processed += segment_duration
            if progress_cb and total_duration > 0:
                progress_cb(processed / total_duration, idx + 1, len(segments))
        finally:
            if segment_path.exists():
                segment_path.unlink()

    return output_segments


def _transcribe_with_faster_whisper(
    audio_path: Path,
    model_name: str,
    language: Optional[str],
    vad_enabled: bool,
    min_silence_ms: int,
    silence_threshold_db: int,
    chunk_seconds: float | None,
    progress_cb: Optional[callable] = None,
) -> list[dict]:
    model = _load_faster_model(model_name)

    segments = _build_segments(
        audio_path,
        vad_enabled=vad_enabled,
        min_silence_ms=min_silence_ms,
        silence_threshold_db=silence_threshold_db,
        chunk_seconds=chunk_seconds,
    )

    if not segments:
        segments = []

    temp_dir = get_temp_dir()
    output_segments: list[dict] = []

    if not segments:
        with _inference_lock:
            seg_iter, _info = model.transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
            )
            for seg in seg_iter:
                output_segments.append(
                    {
                        "start_ms": int(seg.start * 1000),
                        "end_ms": int(seg.end * 1000),
                        "text": seg.text.strip(),
                        "confidence": None,
                    }
                )
        return output_segments

    total_duration = get_wav_duration_seconds(audio_path) or 0.0
    processed = 0.0

    for idx, (start, end) in enumerate(segments):
        segment_duration = end - start
        
        # Skip segments that are too short (Whisper needs at least ~0.5 seconds)
        if segment_duration < 0.5:
            logger.debug(f"Skipping segment {idx}: too short ({segment_duration:.2f}s)")
            processed += segment_duration
            if progress_cb and total_duration > 0:
                progress_cb(processed / total_duration, idx + 1, len(segments))
            continue
        
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, dir=temp_dir
        ) as tmp_file:
            segment_path = Path(tmp_file.name)

        try:
            extract_audio_segment(audio_path, segment_path, start, end)
            
            # Verify segment file was created and has content
            if not segment_path.exists():
                logger.warning(f"Segment file not created: {segment_path}")
                processed += segment_duration
                if progress_cb and total_duration > 0:
                    progress_cb(processed / total_duration, idx + 1, len(segments))
                continue
            
            file_size = segment_path.stat().st_size
            if file_size < 1000:  # Less than 1KB is likely empty/corrupted
                logger.warning(f"Segment file too small ({file_size} bytes), skipping: {segment_path}")
                processed += segment_duration
                if progress_cb and total_duration > 0:
                    progress_cb(processed / total_duration, idx + 1, len(segments))
                continue

            segment_wav_duration = get_wav_duration_seconds(segment_path)
            if segment_wav_duration is None or segment_wav_duration < 0.5:
                logger.warning(
                    "Segment WAV too short after extraction (idx=%d, range=%.2f-%.2fs, "
                    "size=%d bytes, wav_duration=%s) -> skipping",
                    idx,
                    start,
                    end,
                    file_size,
                    f'{segment_wav_duration:.3f}s' if segment_wav_duration is not None else "unknown",
                )
                processed += segment_duration
                if progress_cb and total_duration > 0:
                    progress_cb(processed / total_duration, idx + 1, len(segments))
                continue

            logger.debug(
                "Segment WAV ok (idx=%d, range=%.2f-%.2fs, size=%d bytes, wav_duration=%.3fs)",
                idx,
                start,
                end,
                file_size,
                segment_wav_duration,
            )
            
            with _inference_lock:
                seg_iter, _info = model.transcribe(
                    str(segment_path),
                    language=language,
                    beam_size=5,
                )
                for seg in seg_iter:
                    output_segments.append(
                        {
                            "start_ms": int((seg.start + start) * 1000),
                            "end_ms": int((seg.end + start) * 1000),
                            "text": seg.text.strip(),
                            "confidence": None,
                        }
                    )
            processed += segment_duration
            if progress_cb and total_duration > 0:
                progress_cb(processed / total_duration, idx + 1, len(segments))
        except Exception as e:
            logger.warning(f"Failed to transcribe segment {idx} ({start:.2f}-{end:.2f}s): {e}")
            # Continue with next segment instead of failing entire transcription
            processed += segment_duration
            if progress_cb and total_duration > 0:
                progress_cb(processed / total_duration, idx + 1, len(segments))
        finally:
            if segment_path.exists():
                segment_path.unlink()

    return output_segments


async def transcribe_audio(
    audio_path: Path,
    model_name: str = "base",
    language: Optional[str] = None,
    backend: str = "auto",
    vad_enabled: bool = True,
    min_silence_ms: int = 500,
    silence_threshold_db: int = -35,
    chunk_seconds: float | None = 30.0,
    on_progress: Optional[Callable[[float, int, int], None]] = None,
) -> list[dict]:
    """
    Transcribe audio file using Whisper.

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.)
        model_name: Whisper model name (tiny, base, small, medium, large)
        language: Language code (optional, auto-detect if None)

    Returns:
        List of segments with start_ms, end_ms, text, confidence
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info(f"Transcribing {audio_path} with Whisper {model_name}")

    loop = asyncio.get_running_loop()

    def report_progress(progress: float, chunk_index: int, chunk_total: int) -> None:
        if not on_progress:
            return
        try:
            loop.call_soon_threadsafe(on_progress, progress, chunk_index, chunk_total)
        except RuntimeError:
            # Event loop is closed or unavailable
            pass

    def _run_transcription() -> list[dict]:
        selected_backend = backend
        if selected_backend == "auto":
            selected_backend = "faster-whisper" if _FAST_WHISPER_AVAILABLE else "openai"

        if selected_backend == "faster-whisper":
            if not _FAST_WHISPER_AVAILABLE:
                logger.warning("faster-whisper not available, falling back to OpenAI Whisper")
                selected_backend = "openai"
            else:
                return _transcribe_with_faster_whisper(
                    audio_path=audio_path,
                    model_name=model_name,
                    language=language,
                    vad_enabled=vad_enabled,
                    min_silence_ms=min_silence_ms,
                    silence_threshold_db=silence_threshold_db,
                    chunk_seconds=chunk_seconds,
                    progress_cb=report_progress,
                )

        return _transcribe_with_openai(
            audio_path=audio_path,
            model_name=model_name,
            language=language,
            vad_enabled=vad_enabled,
            min_silence_ms=min_silence_ms,
            silence_threshold_db=silence_threshold_db,
            chunk_seconds=chunk_seconds,
            progress_cb=report_progress,
        )

    segments = await asyncio.to_thread(_run_transcription)
    logger.info(f"Transcription complete: {len(segments)} segments")
    return segments
