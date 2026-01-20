"""Authentication middleware for bearer token validation."""

import os
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..utils.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer token security scheme - auto_error=False allows missing headers
security = HTTPBearer(auto_error=False)


def get_auth_token() -> str | None:
    """Get the auth token from environment variable."""
    return os.environ.get("GAZE_AUTH_TOKEN")


def is_dev_mode() -> bool:
    """Check if running in development mode."""
    # Dev mode if log level is DEBUG or explicitly set
    log_level = os.environ.get("GAZE_LOG_LEVEL", "INFO").upper()
    return log_level == "DEBUG" or os.environ.get("GAZE_DEV_MODE") == "1"


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> str:
    """
    Verify bearer token from request.

    Args:
        credentials: HTTP Bearer credentials from request (optional)

    Returns:
        The validated token or "dev-token" in dev mode

    Raises:
        HTTPException: If token is missing or invalid (in production mode)
    """
    # Dev mode bypasses all auth - check this first
    if is_dev_mode():
        logger.debug("Dev mode enabled - allowing request without auth")
        return credentials.credentials if credentials else "dev-token"

    expected_token = get_auth_token()

    # If no token configured, allow all requests
    if not expected_token:
        logger.debug("No GAZE_AUTH_TOKEN set - allowing request")
        return credentials.credentials if credentials else "dev-token"

    # If credentials provided, validate them
    if credentials:
        token = credentials.credentials
        if token == expected_token:
            logger.debug("Token verified successfully")
            return token
        else:
            logger.warning("Invalid token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Production mode requires credentials
    logger.warning("Missing Authorization header")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
