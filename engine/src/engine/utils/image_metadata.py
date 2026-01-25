"""Image metadata extraction utilities for photos."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging import get_logger

logger = get_logger(__name__)


def _rational_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(value[0]) / float(value[1])
        except Exception:
            return None


def _convert_gps_to_degrees(value: Any) -> float | None:
    if not value:
        return None
    try:
        d = _rational_to_float(value[0])
        m = _rational_to_float(value[1])
        s = _rational_to_float(value[2])
        if d is None or m is None or s is None:
            return None
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return None


def _parse_exif_date(exif_str: str | None) -> str | None:
    """Convert EXIF date '2024:01:15 14:30:00' to ISO '2024-01-15T14:30:00'."""
    if not exif_str:
        return None

    exif_str = str(exif_str).strip()

    try:
        # EXIF format: "YYYY:MM:DD HH:MM:SS"
        dt = datetime.strptime(exif_str, "%Y:%m:%d %H:%M:%S")
        iso_date = dt.isoformat()
        return iso_date
    except Exception as e1:
        # Try alternate format without time
        try:
            dt = datetime.strptime(exif_str, "%Y:%m:%d")
            iso_date = dt.isoformat()
            return iso_date
        except Exception as e2:
            # Try with dashes instead of colons (already ISO-ish)
            try:
                dt = datetime.fromisoformat(exif_str.replace(" ", "T"))
                return dt.isoformat()
            except Exception as e3:
                from ..utils.logging import get_logger
                logger = get_logger(__name__)
                logger.warning(f"Failed to parse EXIF date '{exif_str}': {e1}, {e2}, {e3}")
                return None


def _get_image_metadata_sync(image_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "width": None,
        "height": None,
        "creation_time": None,
        "camera_make": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lng": None,
        "extra_metadata": {},
    }

    try:
        from PIL import Image, ExifTags  # type: ignore[import-not-found]
    except Exception as e:
        logger.warning(f"Pillow not available for image metadata: {e}")
        return result

    try:
        with Image.open(image_path) as img:
            result["width"], result["height"] = img.size

            exif = img.getexif()
            if not exif:
                return result

            tags = ExifTags.TAGS
            gps_tags = ExifTags.GPSTAGS

            exif_data: dict[str, Any] = {}
            for key, value in exif.items():
                tag = tags.get(key, key)
                exif_data[str(tag)] = value

            creation_time = (
                exif_data.get("DateTimeOriginal")
                or exif_data.get("DateTimeDigitized")
                or exif_data.get("DateTime")
            )
            if isinstance(creation_time, bytes):
                try:
                    creation_time = creation_time.decode(errors="ignore")
                except Exception:
                    pass
            # Parse EXIF date to ISO format
            result["creation_time"] = _parse_exif_date(creation_time)

            result["camera_make"] = exif_data.get("Make")
            result["camera_model"] = exif_data.get("Model")

            gps_info = exif.get(34853)
            if gps_info:
                gps_data: dict[str, Any] = {}
                for key, value in gps_info.items():
                    tag = gps_tags.get(key, key)
                    gps_data[str(tag)] = value

                lat = _convert_gps_to_degrees(gps_data.get("GPSLatitude"))
                lon = _convert_gps_to_degrees(gps_data.get("GPSLongitude"))
                lat_ref = gps_data.get("GPSLatitudeRef")
                lon_ref = gps_data.get("GPSLongitudeRef")
                if lat is not None and lat_ref in ("S", "s"):
                    lat = -lat
                if lon is not None and lon_ref in ("W", "w"):
                    lon = -lon

                result["gps_lat"] = lat
                result["gps_lng"] = lon

            extra_fields = {
                "Orientation": exif_data.get("Orientation"),
                "LensModel": exif_data.get("LensModel"),
                "Software": exif_data.get("Software"),
                "ISO": exif_data.get("ISOSpeedRatings"),
                "ExposureTime": exif_data.get("ExposureTime"),
                "FNumber": exif_data.get("FNumber"),
                "FocalLength": exif_data.get("FocalLength"),
            }

            for key, value in extra_fields.items():
                if value is None:
                    continue
                if isinstance(value, bytes):
                    try:
                        value = value.decode(errors="ignore")
                    except Exception:
                        value = str(value)
                result["extra_metadata"][key] = str(value)

    except Exception as e:
        logger.warning(f"Failed to extract image metadata from {image_path}: {e}")

    return result


async def get_image_metadata(image_path: Path) -> dict[str, Any]:
    """Extract photo metadata (EXIF + dimensions)."""
    return await asyncio.to_thread(_get_image_metadata_sync, image_path)
