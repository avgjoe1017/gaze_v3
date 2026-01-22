"""OpenCLIP embedding wrapper."""

import numpy as np
from pathlib import Path
from typing import Optional

from ..utils.logging import get_logger
from ..utils.paths import get_models_dir

logger = get_logger(__name__)

# Check if open_clip is available
try:
    import open_clip
    import torch

    _OPENCLIP_AVAILABLE = True
except ImportError:
    _OPENCLIP_AVAILABLE = False
    logger.warning("OpenCLIP not available. Install with: pip install open-clip-torch torch")


_model_cache: Optional[tuple] = None


def _load_openclip_checkpoint(model, checkpoint_path: Path) -> None:
    """Load a local OpenCLIP checkpoint into the model."""
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    if isinstance(checkpoint, dict):
        if "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        elif "model" in checkpoint:
            state_dict = checkpoint["model"]
        else:
            state_dict = checkpoint
    else:
        raise ValueError("Unexpected OpenCLIP checkpoint format")

    cleaned_state = {}
    for key, value in state_dict.items():
        if key.startswith("module."):
            key = key[7:]
        cleaned_state[key] = value

    missing, unexpected = model.load_state_dict(cleaned_state, strict=False)
    if missing:
        logger.warning(f"OpenCLIP checkpoint missing keys: {len(missing)}")
    if unexpected:
        logger.warning(f"OpenCLIP checkpoint unexpected keys: {len(unexpected)}")


def _load_model(model_name: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k") -> tuple:
    """Load and cache OpenCLIP model."""
    global _model_cache

    if not _OPENCLIP_AVAILABLE:
        raise RuntimeError(
            "OpenCLIP is not installed. Install with: pip install open-clip-torch torch"
        )

    if _model_cache is None:
        models_dir = get_models_dir()
        model_path = models_dir / "openclip-vit-b-32.bin"
        
        logger.info(f"Loading OpenCLIP model: {model_name}/{pretrained}")
        
        # Try to load from downloaded model file if available
        if model_path.exists():
            logger.debug(f"Loading OpenCLIP model from {model_path}")
            try:
                model, _, preprocess = open_clip.create_model_and_transforms(
                    model_name, pretrained=None
                )
                _load_openclip_checkpoint(model, model_path)
            except Exception as e:
                logger.warning(f"Failed to load from {model_path}, using default: {e}")
                # Fallback to default pretrained
                model, _, preprocess = open_clip.create_model_and_transforms(
                    model_name, pretrained=pretrained
                )
        else:
            # Use default pretrained (downloads if needed)
            model, _, preprocess = open_clip.create_model_and_transforms(
                model_name, pretrained=pretrained
            )
        
        model.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)

        tokenizer = open_clip.get_tokenizer(model_name)
        _model_cache = (model, preprocess, tokenizer, device)
        logger.info(f"OpenCLIP model loaded on {device}")

    return _model_cache


async def embed_image(image_path: Path) -> np.ndarray:
    """
    Generate embedding for an image using OpenCLIP.

    Args:
        image_path: Path to image file

    Returns:
        Normalized embedding vector (512-dim for ViT-B-32)
    """
    if not _OPENCLIP_AVAILABLE:
        raise RuntimeError(
            "OpenCLIP is not installed. Install with: pip install open-clip-torch torch"
        )

    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    from PIL import Image

    model, preprocess, tokenizer, device = _load_model()

    # Load and preprocess image
    image = Image.open(image_path).convert("RGB")
    image_tensor = preprocess(image).unsqueeze(0).to(device)

    # Generate embedding
    with torch.no_grad():
        image_features = model.encode_image(image_tensor)
        # Normalize
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

    # Convert to numpy
    embedding = image_features.cpu().numpy().flatten()

    return embedding


async def embed_text(text: str) -> np.ndarray:
    """
    Generate embedding for text using OpenCLIP.

    Args:
        text: Text string to embed

    Returns:
        Normalized embedding vector (512-dim for ViT-B-32)
    """
    if not _OPENCLIP_AVAILABLE:
        raise RuntimeError(
            "OpenCLIP is not installed. Install with: pip install open-clip-torch torch"
        )

    model, preprocess, tokenizer, device = _load_model()

    # Tokenize and encode text
    text_tokens = tokenizer([text]).to(device)

    # Generate embedding
    with torch.no_grad():
        text_features = model.encode_text(text_tokens)
        # Normalize
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    # Convert to numpy
    embedding = text_features.cpu().numpy().flatten()

    return embedding
