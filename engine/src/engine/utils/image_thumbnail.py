"""Image thumbnail utilities for photo indexing."""

from __future__ import annotations

from pathlib import Path

from .logging import get_logger

logger = get_logger(__name__)


# Grid thumbnail settings - optimized for fast loading in media grid
GRID_MAX_DIMENSION = 256
GRID_QUALITY = 50

# Full thumbnail settings - for lightbox/detail view
FULL_MAX_DIMENSION = 1280
FULL_QUALITY = 85


def create_photo_thumbnail(
    source_path: Path,
    output_path: Path,
    max_dimension: int = FULL_MAX_DIMENSION,
    quality: int = FULL_QUALITY,
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


def create_grid_thumbnail(
    source_path: Path,
    output_path: Path,
    max_dimension: int = GRID_MAX_DIMENSION,
    quality: int = GRID_QUALITY,
) -> None:
    """
    Create a small, fast-loading thumbnail optimized for grid display.

    Uses aggressive compression for quick loading while maintaining
    acceptable visual quality at small display sizes.
    """
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
            # Use BILINEAR for speed on grid thumbnails (LANCZOS is slower)
            img = img.resize(new_size, Image.BILINEAR)

        # Save with progressive JPEG for perceived faster loading
        img.save(
            output_path,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )

    logger.debug(f"Created grid thumbnail: {output_path}")


def create_grid_thumbnail_from_full(
    full_thumbnail_path: Path,
    grid_output_path: Path,
    max_dimension: int = GRID_MAX_DIMENSION,
    quality: int = GRID_QUALITY,
) -> None:
    """
    Create a grid thumbnail from an existing full-size thumbnail.

    This is more efficient than re-reading the original source file
    when the full thumbnail already exists.
    """
    create_grid_thumbnail(full_thumbnail_path, grid_output_path, max_dimension, quality)
