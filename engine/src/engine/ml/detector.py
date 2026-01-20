"""Torchvision object detection wrapper (SSDLite MobileNetV3)."""

from pathlib import Path
from typing import Optional, Callable, Any

from PIL import Image

from ..utils.logging import get_logger
from ..utils.paths import get_models_dir

logger = get_logger(__name__)

# Check if torchvision is available
try:
    import torch
    from torchvision.models.detection import (
        ssdlite320_mobilenet_v3_large,
        SSDLite320_MobileNet_V3_Large_Weights,
    )

    _DETECTOR_AVAILABLE = True
except ImportError:
    _DETECTOR_AVAILABLE = False
    logger.warning("SSDLite detector not available. Install with: pip install torchvision")


_ModelCache = tuple[object, list[str], Callable[[Image.Image], Any], object]
_model_cache: Optional[_ModelCache] = None


def _load_model() -> _ModelCache:
    """Load and cache the SSDLite model."""
    global _model_cache

    if not _DETECTOR_AVAILABLE:
        raise RuntimeError("SSDLite detector is not installed. Install with: pip install torchvision")

    if _model_cache is None:
        models_dir = get_models_dir()
        model_path = models_dir / "ssdlite320_mobilenet_v3_large_coco.pth"

        weights = SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
        categories = list(weights.meta.get("categories", []))

        # Use downloaded model if available, otherwise use torchvision download
        if model_path.exists():
            logger.info(f"Loading SSDLite model from {model_path}")
            # Match the weights architecture by disabling backbone weights.
            model = ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None)
            state_dict = torch.load(model_path, map_location="cpu")
            model.load_state_dict(state_dict)
        else:
            logger.info("Loading SSDLite model weights (will download if needed)")
            model = ssdlite320_mobilenet_v3_large(weights=weights)

        model.eval()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        preprocess = weights.transforms()

        _model_cache = (model, categories, preprocess, device)

        logger.info("SSDLite model loaded")

    return _model_cache


async def detect_objects(image_path: Path, confidence_threshold: float = 0.25) -> list[dict]:
    """
    Detect objects in an image using SSDLite MobileNetV3.

    Args:
        image_path: Path to image file
        confidence_threshold: Minimum confidence for detections (0.0-1.0)

    Returns:
        List of detections with label, confidence, bbox (x, y, w, h)
    """
    if not _DETECTOR_AVAILABLE:
        raise RuntimeError("SSDLite detector is not installed. Install with: pip install torchvision")

    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    model, categories, preprocess, device = _load_model()
    image = Image.open(image_path).convert("RGB")
    input_tensor = preprocess(image).unsqueeze(0).to(device)

    # Run detection
    with torch.no_grad():
        output = model(input_tensor)[0]

    # Extract detections
    detections = []
    scores = output.get("scores")
    labels = output.get("labels")
    boxes = output.get("boxes")

    if scores is None or labels is None or boxes is None:
        return detections

    scores = scores.detach().cpu().tolist()
    labels = labels.detach().cpu().tolist()
    boxes = boxes.detach().cpu().tolist()

    for score, label_id, box in zip(scores, labels, boxes):
        confidence = float(score)
        if confidence < confidence_threshold:
            continue

        label_index = int(label_id)
        label = categories[label_index] if 0 <= label_index < len(categories) else str(label_index)

        x1, y1, x2, y2 = box
        detections.append({
            "label": label,
            "confidence": confidence,
            "bbox_x": float(x1),
            "bbox_y": float(y1),
            "bbox_w": float(x2 - x1),
            "bbox_h": float(y2 - y1),
        })

    return detections
