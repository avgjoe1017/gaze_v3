"""FFmpeg utilities for video processing."""

import asyncio
import subprocess
from pathlib import Path

from .logging import get_logger

logger = get_logger(__name__)


async def extract_audio(video_path: Path, output_path: Path, sample_rate: int = 16000) -> None:
    """
    Extract audio from video as WAV file using FFmpeg.

    Args:
        video_path: Path to input video file
        output_path: Path to output WAV file
        sample_rate: Output sample rate in Hz (default 16000 for Whisper)
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Extracting audio from {video_path} to {output_path}")

    # FFmpeg command: extract audio, convert to 16kHz mono WAV
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", str(sample_rate),  # Sample rate
        "-ac", "1",  # Mono
        "-y",  # Overwrite output file
        str(output_path),
    ]

    # Run FFmpeg asynchronously
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
        raise RuntimeError(f"FFmpeg audio extraction failed: {error_msg}")

    if not output_path.exists():
        raise RuntimeError(f"Output audio file was not created: {output_path}")

    logger.info(f"Audio extracted: {output_path}")


async def extract_frames(
    video_path: Path,
    output_dir: Path,
    interval_seconds: float = 2.0,
    image_format: str = "jpg",
) -> list[Path]:
    """
    Extract frames from video at regular intervals using FFmpeg.

    Args:
        video_path: Path to input video file
        output_dir: Directory to save extracted frames
        interval_seconds: Time interval between frames in seconds (default 2.0)
        image_format: Output image format (jpg, png, etc.)

    Returns:
        List of paths to extracted frame images
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Extracting frames from {video_path} to {output_dir} (every {interval_seconds}s)")

    # FFmpeg command: extract frames at regular intervals
    # Using select filter for precise timing
    output_pattern = str(output_dir / f"frame_%06d.{image_format}")

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", f"fps=1/{interval_seconds}",
        "-q:v", "2",  # High quality JPEG
        "-y",  # Overwrite output files
        output_pattern,
    ]

    # Run FFmpeg asynchronously
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
        # Non-critical: log warning but continue (might be empty video or other issue)
        logger.warning(f"FFmpeg frame extraction had issues: {error_msg}")

    # Collect extracted frame paths
    frame_paths = sorted(output_dir.glob(f"frame_*.{image_format}"))

    if not frame_paths:
        logger.warning(f"No frames extracted from {video_path}")

    logger.info(f"Extracted {len(frame_paths)} frames to {output_dir}")
    return frame_paths


def get_wav_duration_seconds(audio_path: Path) -> float | None:
    """Get WAV duration in seconds using the wave module."""
    if not audio_path.exists():
        return None

    try:
        import wave

        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate == 0:
                return None
            return frames / float(rate)
    except Exception as e:
        logger.debug(f"Failed to read WAV duration for {audio_path}: {e}")
        return None


def detect_nonsilent_segments(
    audio_path: Path,
    min_silence_ms: int = 500,
    silence_threshold_db: int = -35,
) -> list[tuple[float, float]]:
    """
    Detect non-silent segments using ffmpeg silencedetect.

    Returns list of (start_seconds, end_seconds) segments.
    """
    if not audio_path.exists():
        return []

    min_silence_s = max(min_silence_ms, 100) / 1000.0

    cmd = [
        "ffmpeg",
        "-i", str(audio_path),
        "-af", f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_s}",
        "-f", "null",
        "-",
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
    except Exception as e:
        logger.warning(f"Failed to run silencedetect: {e}")
        return []

    silence_starts: list[float] = []
    silence_ends: list[float] = []

    for line in result.stderr.splitlines():
        if "silence_start:" in line:
            try:
                silence_starts.append(float(line.split("silence_start:")[1].strip()))
            except ValueError:
                continue
        elif "silence_end:" in line:
            try:
                silence_ends.append(float(line.split("silence_end:")[1].split("|")[0].strip()))
            except ValueError:
                continue

    duration = get_wav_duration_seconds(audio_path)
    if duration is None:
        return []

    segments: list[tuple[float, float]] = []
    current = 0.0

    for idx, start in enumerate(silence_starts):
        if start > current:
            segments.append((current, start))
        if idx < len(silence_ends):
            current = max(current, silence_ends[idx])

    if current < duration:
        segments.append((current, duration))

    # Filter out tiny segments
    segments = [(s, e) for s, e in segments if e - s >= 0.2]
    return segments


def extract_audio_segment(
    input_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    """Extract an audio segment to a WAV file using ffmpeg."""
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-ss", f"{start_seconds:.3f}",
        "-to", f"{end_seconds:.3f}",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown FFmpeg error"
        raise RuntimeError(f"FFmpeg segment extraction failed: {error_msg}")
