"""Color extraction utilities for frame analysis."""

from pathlib import Path
from collections import Counter

from PIL import Image
import numpy as np

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Named colors with their RGB ranges (simplified color palette)
# Each color has a name and HSV ranges (hue, sat_min, sat_max, val_min, val_max)
COLOR_DEFINITIONS = {
    # Hue-based colors (hue is 0-180 in OpenCV)
    "red": [(0, 10), (170, 180)],  # Red wraps around
    "orange": [(10, 25)],
    "yellow": [(25, 35)],
    "green": [(35, 85)],
    "cyan": [(85, 100)],
    "blue": [(100, 130)],
    "purple": [(130, 150)],
    "pink": [(150, 170)],
}

# Grayscale colors (determined by saturation and value)
GRAYSCALE_COLORS = {
    "black": (0, 50),      # value range
    "gray": (50, 180),     # value range
    "white": (180, 255),   # value range
}

# Minimum saturation to be considered a "color" vs grayscale
MIN_SATURATION = 30

# Common color name aliases for search
COLOR_ALIASES = {
    "red": ["red", "scarlet", "crimson", "maroon"],
    "orange": ["orange", "tangerine"],
    "yellow": ["yellow", "gold", "golden"],
    "green": ["green", "lime", "olive", "teal"],
    "cyan": ["cyan", "aqua", "turquoise"],
    "blue": ["blue", "navy", "azure", "cobalt"],
    "purple": ["purple", "violet", "magenta", "lavender"],
    "pink": ["pink", "rose", "salmon"],
    "black": ["black", "dark"],
    "gray": ["gray", "grey", "silver"],
    "white": ["white", "cream", "ivory"],
}

# Reverse lookup: alias -> canonical color
ALIAS_TO_COLOR = {}
for color, aliases in COLOR_ALIASES.items():
    for alias in aliases:
        ALIAS_TO_COLOR[alias.lower()] = color


def get_canonical_color(color_query: str) -> str | None:
    """Convert a color query to canonical color name."""
    return ALIAS_TO_COLOR.get(color_query.lower().strip())


def extract_color_from_query(query: str) -> str | None:
    """Extract color word from a search query."""
    words = query.lower().split()
    for word in words:
        if word in ALIAS_TO_COLOR:
            return ALIAS_TO_COLOR[word]
    return None


def rgb_to_hsv(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Convert RGB to HSV (OpenCV-style: H=0-180, S=0-255, V=0-255)."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    # Hue calculation
    if diff == 0:
        h = 0
    elif max_c == r:
        h = (60 * ((g - b) / diff) + 360) % 360
    elif max_c == g:
        h = (60 * ((b - r) / diff) + 120) % 360
    else:
        h = (60 * ((r - g) / diff) + 240) % 360

    # Saturation
    s = 0 if max_c == 0 else (diff / max_c)

    # Value
    v = max_c

    # Convert to OpenCV ranges
    return int(h / 2), int(s * 255), int(v * 255)


def classify_color(h: int, s: int, v: int) -> str:
    """Classify HSV values into a named color."""
    # Check if it's grayscale (low saturation)
    if s < MIN_SATURATION:
        if v < 50:
            return "black"
        elif v < 180:
            return "gray"
        else:
            return "white"

    # Check hue-based colors
    for color_name, hue_ranges in COLOR_DEFINITIONS.items():
        for hue_range in hue_ranges:
            if hue_range[0] <= h <= hue_range[1]:
                return color_name

    return "gray"  # Fallback


async def extract_dominant_colors(image_path: Path, num_colors: int = 5) -> list[str]:
    """
    Extract dominant colors from an image using k-means clustering.

    Args:
        image_path: Path to image file
        num_colors: Number of dominant colors to extract

    Returns:
        List of color names (e.g., ["blue", "white", "black"])
    """
    if not image_path.exists():
        return []

    try:
        # Load and resize image for faster processing
        image = Image.open(image_path).convert("RGB")

        # Resize to speed up processing
        max_size = 150
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        # Convert to numpy array
        pixels = np.array(image).reshape(-1, 3)

        # Simple k-means clustering
        from sklearn.cluster import MiniBatchKMeans

        n_clusters = min(num_colors + 2, len(pixels))  # Extra clusters, we'll filter
        if n_clusters < 2:
            return []

        kmeans = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, n_init=3)
        kmeans.fit(pixels)

        # Get cluster centers and their counts
        centers = kmeans.cluster_centers_
        labels = kmeans.labels_
        counts = Counter(labels)

        # Sort by frequency
        sorted_clusters = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        # Classify each dominant color
        colors = []
        seen_colors = set()

        for cluster_idx, count in sorted_clusters:
            if len(colors) >= num_colors:
                break

            r, g, b = centers[cluster_idx].astype(int)
            h, s, v = rgb_to_hsv(r, g, b)
            color_name = classify_color(h, s, v)

            # Avoid duplicates
            if color_name not in seen_colors:
                colors.append(color_name)
                seen_colors.add(color_name)

        return colors

    except ImportError:
        # Fallback if sklearn not available - use simpler histogram method
        logger.warning("sklearn not available, using histogram-based color extraction")
        return await _extract_colors_histogram(image_path)
    except Exception as e:
        logger.warning(f"Failed to extract colors from {image_path}: {e}")
        return []


async def _extract_colors_histogram(image_path: Path) -> list[str]:
    """Fallback color extraction using histogram analysis."""
    try:
        image = Image.open(image_path).convert("RGB")

        # Resize
        max_size = 100
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        pixels = list(image.getdata())

        # Count colors by classification
        color_counts: Counter = Counter()
        for r, g, b in pixels:
            h, s, v = rgb_to_hsv(r, g, b)
            color_name = classify_color(h, s, v)
            color_counts[color_name] += 1

        # Return top colors
        return [color for color, _ in color_counts.most_common(5)]

    except Exception as e:
        logger.warning(f"Histogram color extraction failed: {e}")
        return []
