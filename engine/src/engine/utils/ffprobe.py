"""FFprobe utilities for extracting video metadata."""

import asyncio
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .ffmpeg import get_ffprobe_path
from .logging import get_logger

logger = get_logger(__name__)


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_rotation(stream: dict) -> int:
    """Extract rotation from stream side_data or tags."""
    # Check side_data_list for rotation
    side_data = stream.get("side_data_list", [])
    for sd in side_data:
        if sd.get("side_data_type") == "Display Matrix" and "rotation" in sd:
            rot = _safe_int(sd["rotation"])
            if rot is not None:
                return abs(rot) % 360

    # Check tags for rotate
    tags = stream.get("tags", {})
    rotate_tag = tags.get("rotate") or tags.get("ROTATE")
    if rotate_tag:
        rot = _safe_int(rotate_tag)
        if rot is not None:
            return abs(rot) % 360

    return 0


def _parse_gps_coordinate(value: str) -> float | None:
    """Parse GPS coordinate from various formats."""
    if not value:
        return None

    # Try direct float parsing first
    try:
        return float(value)
    except ValueError:
        pass

    # Parse DMS format like "40 deg 26' 46.80\" N" or "+40.4463"
    # Also handles ISO 6709 format like "+40.4463-073.5789/"
    match = re.match(r'([+-]?\d+\.?\d*)', value.strip())
    if match:
        return float(match.group(1))

    return None


async def get_video_metadata(video_path: Path) -> dict:
    """
    Extract comprehensive video metadata using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        Dictionary with all available metadata fields:
        - duration_ms, width, height (basic)
        - fps, video_codec, video_bitrate (video technical)
        - audio_codec, audio_channels, audio_sample_rate (audio technical)
        - container_format, rotation (container info)
        - creation_time, camera_make, camera_model (source info)
        - gps_lat, gps_lng (location)
        - extra_metadata (dict of additional key-value pairs)
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    logger.debug(f"Extracting metadata from {video_path}")

    # FFprobe command to get comprehensive JSON output
    cmd = [
        get_ffprobe_path(),
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(video_path),
    ]

    # Default result with all fields
    result: dict = {
        # Basic
        "duration_ms": None,
        "width": None,
        "height": None,
        # Video technical
        "fps": None,
        "video_codec": None,
        "video_bitrate": None,
        # Audio technical
        "audio_codec": None,
        "audio_channels": None,
        "audio_sample_rate": None,
        # Container
        "container_format": None,
        "rotation": 0,
        # Source/creation
        "creation_time": None,
        "camera_make": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lng": None,
        # Extra metadata for flexible storage
        "extra_metadata": {},
    }

    try:
        # Run ffprobe
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown ffprobe error"
            logger.warning(f"FFprobe failed for {video_path}: {error_msg}")
            return result

        # Parse JSON output
        data = json.loads(stdout.decode())

        # Extract format-level metadata
        format_info = data.get("format", {})
        format_tags = format_info.get("tags", {})

        # Duration
        if "duration" in format_info:
            duration_seconds = _safe_float(format_info["duration"])
            if duration_seconds is not None:
                result["duration_ms"] = int(duration_seconds * 1000)

        # Container format
        result["container_format"] = format_info.get("format_name")

        # Creation time from format tags (multiple possible keys)
        creation_time = (
            format_tags.get("creation_time") or
            format_tags.get("date") or
            format_tags.get("DATE") or
            format_tags.get("com.apple.quicktime.creationdate")
        )
        if creation_time:
            result["creation_time"] = creation_time

        # Camera/device info from format tags
        result["camera_make"] = (
            format_tags.get("make") or
            format_tags.get("MAKE") or
            format_tags.get("com.apple.quicktime.make") or
            format_tags.get("manufacturer")
        )
        result["camera_model"] = (
            format_tags.get("model") or
            format_tags.get("MODEL") or
            format_tags.get("com.apple.quicktime.model") or
            format_tags.get("product")
        )

        # GPS coordinates from format tags
        gps_location = (
            format_tags.get("location") or
            format_tags.get("LOCATION") or
            format_tags.get("com.apple.quicktime.location.ISO6709")
        )
        if gps_location:
            # Parse ISO 6709 format: "+40.4463-073.5789/"
            match = re.match(r'([+-]\d+\.?\d*)([+-]\d+\.?\d*)', gps_location)
            if match:
                result["gps_lat"] = _safe_float(match.group(1))
                result["gps_lng"] = _safe_float(match.group(2))

        # Also check separate lat/lng tags
        if result["gps_lat"] is None:
            result["gps_lat"] = _parse_gps_coordinate(
                format_tags.get("location-lat") or format_tags.get("latitude")
            )
        if result["gps_lng"] is None:
            result["gps_lng"] = _parse_gps_coordinate(
                format_tags.get("location-lon") or format_tags.get("longitude")
            )

        # Collect extra metadata (title, encoder, etc.)
        extra_keys = ["title", "encoder", "handler_name", "copyright", "description", "artist", "album"]
        for key in extra_keys:
            value = format_tags.get(key) or format_tags.get(key.upper())
            if value:
                result["extra_metadata"][key] = value

        # Process streams
        streams = data.get("streams", [])
        video_stream_found = False
        audio_stream_found = False

        for stream in streams:
            codec_type = stream.get("codec_type")

            if codec_type == "video" and not video_stream_found:
                video_stream_found = True
                stream_tags = stream.get("tags", {})

                # Dimensions
                result["width"] = _safe_int(stream.get("width"))
                result["height"] = _safe_int(stream.get("height"))

                # Codec
                result["video_codec"] = stream.get("codec_name")

                # Bitrate (from stream or calculate from format)
                result["video_bitrate"] = _safe_int(stream.get("bit_rate"))
                if result["video_bitrate"] is None:
                    # Try to get from format level
                    result["video_bitrate"] = _safe_int(format_info.get("bit_rate"))

                # Frame rate (prefer avg_frame_rate, fallback to r_frame_rate)
                fps_str = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
                if fps_str and "/" in fps_str:
                    try:
                        num, den = fps_str.split("/")
                        num_f = float(num)
                        den_f = float(den)
                        if den_f > 0:
                            result["fps"] = round(num_f / den_f, 3)
                    except (ValueError, ZeroDivisionError):
                        pass
                elif fps_str:
                    result["fps"] = _safe_float(fps_str)

                # Rotation
                result["rotation"] = _parse_rotation(stream)

                # Check stream tags for creation time if not found yet
                if not result["creation_time"]:
                    result["creation_time"] = stream_tags.get("creation_time")

            elif codec_type == "audio" and not audio_stream_found:
                audio_stream_found = True

                # Audio codec
                result["audio_codec"] = stream.get("codec_name")

                # Channels
                result["audio_channels"] = _safe_int(stream.get("channels"))

                # Sample rate
                result["audio_sample_rate"] = _safe_int(stream.get("sample_rate"))

        logger.debug(f"Metadata extracted: duration={result['duration_ms']}ms, "
                     f"{result['width']}x{result['height']}, "
                     f"fps={result['fps']}, codec={result['video_codec']}")
        return result

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse ffprobe JSON output: {e}")
        return result
    except Exception as e:
        logger.warning(f"FFprobe error for {video_path}: {e}")
        return result
