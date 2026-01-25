"""Origin header validation middleware."""

import logging
import os
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..utils.logging import get_logger

logger = get_logger(__name__)


def _is_debug_mode() -> bool:
    """Check if we're in debug mode by checking log level."""
    # Check environment variable first (set by main())
    log_level = os.environ.get("GAZE_LOG_LEVEL", "").upper()
    if log_level == "DEBUG":
        return True
    
    # Fallback: check if root logger is set to DEBUG
    root_logger = logging.getLogger()
    if root_logger.level == logging.DEBUG:
        return True
    
    return False


def _get_allowed_origins() -> set[str]:
    """Get allowed origins based on debug mode."""
    origins = {"tauri://localhost"}  # Always allow Tauri origin
    
    # In debug mode, also allow dev server
    if _is_debug_mode():
        origins.add("http://localhost:1420")
    
    return origins


class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate Origin header against allowlist."""

    async def dispatch(self, request: Request, call_next):
        """Validate Origin header before processing request."""
        # Skip validation for health endpoint (needed for startup checks)
        if request.url.path == "/health":
            return await call_next(request)

        # Get allowed origins dynamically (checks debug mode)
        allowed_origins = _get_allowed_origins()
        
        origin = request.headers.get("origin")
        
        # If Origin header is present, validate it
        if origin:
            # Remove trailing slash and normalize
            origin_normalized = origin.rstrip("/")
            
            if origin_normalized not in allowed_origins:
                logger.warning(f"Rejected request from unauthorized origin: {origin}")
                return Response(
                    content='{"detail":"Origin not allowed"}',
                    status_code=status.HTTP_403_FORBIDDEN,
                    media_type="application/json",
                )
        
        # For requests without Origin (e.g., same-origin), allow if Referer is from allowed origin
        # This handles cases where browser doesn't send Origin header
        referer = request.headers.get("referer")
        if referer and not origin:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(referer)
                referer_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
                
                if referer_origin not in allowed_origins:
                    logger.warning(f"Rejected request with unauthorized referer: {referer_origin}")
                    return Response(
                        content='{"detail":"Referer not allowed"}',
                        status_code=status.HTTP_403_FORBIDDEN,
                        media_type="application/json",
                    )
            except Exception as e:
                logger.debug(f"Failed to parse referer: {e}")

        return await call_next(request)
