"""Image thumbnail utilities for photo indexing."""

from __future__ import annotations

from pathlib import Path

from .logging import get_logger

logger = get_logger(__name__)


def create_photo_thumbnail(
    source_path: Path,
    output_path: Path,
    max_dimension: int = 1280,
    quality: int = 85,
) -> None:
    """Create a JPEG thumbnail for a photo, respecting EXIF orientation."""
    try:
        from PIL import Image, ImageOps  # type: ignore[import-not-found]
    except Exception as e:
        raise RuntimeError(f"Pillow not available for thumbnailing: {e}") from e

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")

        width, height = img.size
        max_current = max(width, height)
        if max_current > max_dimension:
            scale = max_dimension / max_current
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            img = img.resize(new_size, Image.LANCZOS)

        img.save(output_path, format="JPEG", quality=quality, optimize=True)

    logger.debug(f"Created photo thumbnail: {output_path}")
