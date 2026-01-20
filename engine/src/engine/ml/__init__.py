"""ML model wrappers for Gaze Engine."""

from .detector import detect_objects
from .embedder import embed_image
from .whisper import transcribe_audio

__all__ = ["transcribe_audio", "embed_image", "detect_objects"]
