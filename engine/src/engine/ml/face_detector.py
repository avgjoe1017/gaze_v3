"""Face detection and embedding using InsightFace (RetinaFace + ArcFace)."""

import numpy as np
from pathlib import Path
from typing import Optional
import io

from PIL import Image

from ..utils.logging import get_logger
from ..utils.paths import get_models_dir, get_data_dir

logger = get_logger(__name__)

# Check if insightface is available
try:
    import insightface
    from insightface.app import FaceAnalysis
    import cv2
    _INSIGHTFACE_AVAILABLE = True
except ImportError:
    _INSIGHTFACE_AVAILABLE = False
    logger.warning("InsightFace not available. Install with: pip install insightface onnxruntime")


_face_app_cache: Optional["FaceAnalysis"] = None


def _load_face_app() -> "FaceAnalysis":
    """Load and cache the InsightFace app."""
    global _face_app_cache

    if not _INSIGHTFACE_AVAILABLE:
        raise RuntimeError(
            "InsightFace is not installed. Install with: pip install insightface onnxruntime"
        )

    if _face_app_cache is None:
        models_dir = get_models_dir() / "insightface"
        models_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Loading InsightFace model (buffalo_l)...")

        # Create FaceAnalysis app with buffalo_l model (good balance of speed/accuracy)
        # buffalo_l includes: det_10g (detection) + w600k_r50 (recognition)
        app = FaceAnalysis(
            name="buffalo_l",
            root=str(models_dir),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )

        # Prepare with detection size (640 is good for most use cases)
        # det_size affects detection accuracy vs speed
        app.prepare(ctx_id=0, det_size=(640, 640))

        _face_app_cache = app
        logger.info("InsightFace model loaded")

    return _face_app_cache


def get_faces_dir() -> Path:
    """Get the directory for face crops."""
    path = get_data_dir() / "faces"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def detect_faces(
    image_path: Path,
    min_face_size: int = 20,
    det_thresh: float = 0.5,
) -> list[dict]:
    """
    Detect faces in an image and extract embeddings.

    Args:
        image_path: Path to image file
        min_face_size: Minimum face size in pixels to detect
        det_thresh: Detection confidence threshold (0.0-1.0)

    Returns:
        List of detected faces with:
        - bbox_x, bbox_y, bbox_w, bbox_h: Bounding box
        - confidence: Detection confidence
        - embedding: 512-dim face embedding (numpy array)
        - landmarks: 5-point facial landmarks
        - age: Estimated age (optional)
        - gender: Estimated gender (optional)
    """
    if not _INSIGHTFACE_AVAILABLE:
        raise RuntimeError(
            "InsightFace is not installed. Install with: pip install insightface onnxruntime"
        )

    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    app = _load_face_app()

    # Load image using OpenCV (InsightFace expects BGR)
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    # Detect faces
    faces = app.get(img)

    results = []
    for face in faces:
        # Filter by confidence
        if face.det_score < det_thresh:
            continue

        # Get bounding box (x1, y1, x2, y2)
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1

        # Filter by minimum size
        if width < min_face_size or height < min_face_size:
            continue

        result = {
            "bbox_x": float(x1),
            "bbox_y": float(y1),
            "bbox_w": float(width),
            "bbox_h": float(height),
            "confidence": float(face.det_score),
            "embedding": face.normed_embedding,  # 512-dim normalized embedding
            "landmarks": face.kps.tolist() if face.kps is not None else None,
        }

        # Add age/gender if available
        if hasattr(face, "age") and face.age is not None:
            result["age"] = int(face.age)
        if hasattr(face, "gender") and face.gender is not None:
            result["gender"] = "male" if face.gender == 1 else "female"

        results.append(result)

    return results


async def extract_face_crop(
    image_path: Path,
    bbox: tuple[float, float, float, float],
    output_path: Path,
    padding: float = 0.3,
    size: tuple[int, int] = (112, 112),
) -> None:
    """
    Extract and save a face crop from an image.

    Args:
        image_path: Path to source image
        bbox: Bounding box (x, y, w, h)
        output_path: Path to save the crop
        padding: Extra padding around face (as fraction of face size)
        size: Output size (width, height)
    """
    img = Image.open(image_path).convert("RGB")
    img_w, img_h = img.size

    x, y, w, h = bbox

    # Add padding
    pad_w = w * padding
    pad_h = h * padding

    x1 = max(0, int(x - pad_w))
    y1 = max(0, int(y - pad_h))
    x2 = min(img_w, int(x + w + pad_w))
    y2 = min(img_h, int(y + h + pad_h))

    # Crop and resize
    crop = img.crop((x1, y1, x2, y2))
    crop = crop.resize(size, Image.Resampling.LANCZOS)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output_path, "JPEG", quality=90)


def compute_face_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    Compute cosine similarity between two face embeddings.

    Args:
        embedding1: First face embedding (512-dim)
        embedding2: Second face embedding (512-dim)

    Returns:
        Similarity score (0.0-1.0, higher = more similar)
    """
    # Embeddings should already be normalized, but ensure
    e1 = embedding1 / np.linalg.norm(embedding1)
    e2 = embedding2 / np.linalg.norm(embedding2)

    # Cosine similarity
    similarity = float(np.dot(e1, e2))

    # Convert from [-1, 1] to [0, 1]
    return (similarity + 1) / 2


def is_same_person(
    embedding1: np.ndarray,
    embedding2: np.ndarray,
    threshold: float = 0.6,
) -> tuple[bool, float]:
    """
    Determine if two face embeddings belong to the same person.

    Args:
        embedding1: First face embedding
        embedding2: Second face embedding
        threshold: Similarity threshold (default 0.6 works well for ArcFace)

    Returns:
        Tuple of (is_same_person, similarity_score)
    """
    similarity = compute_face_similarity(embedding1, embedding2)
    return similarity >= threshold, similarity


async def find_matching_person(
    embedding: np.ndarray,
    known_embeddings: list[tuple[str, np.ndarray]],
    threshold: float = 0.6,
) -> Optional[tuple[str, float]]:
    """
    Find the best matching person from a list of known face embeddings.

    Args:
        embedding: Face embedding to match
        known_embeddings: List of (person_id, embedding) tuples
        threshold: Minimum similarity threshold

    Returns:
        Tuple of (person_id, similarity) if match found, None otherwise
    """
    best_match = None
    best_similarity = threshold

    for person_id, known_embedding in known_embeddings:
        similarity = compute_face_similarity(embedding, known_embedding)
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = person_id

    if best_match is not None:
        return best_match, best_similarity

    return None


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Convert a face embedding to bytes for storage."""
    return embedding.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Convert bytes back to a face embedding."""
    return np.frombuffer(data, dtype=np.float32)
