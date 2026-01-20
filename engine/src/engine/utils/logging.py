"""Logging configuration for Gaze Engine."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .paths import get_data_dir

_logger_cache: dict[str, logging.Logger] = {}
_log_file_handler: logging.Handler | None = None


def setup_logging(level: str = "INFO", module_levels: dict[str, str] | None = None) -> None:
    """Set up logging configuration.
    
    Args:
        level: Root log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        module_levels: Dict mapping module names to their log levels
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    module_levels = module_levels or {}

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove existing handlers
    global _log_file_handler
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    if _log_file_handler:
        _log_file_handler.close()
        _log_file_handler = None

    # Add stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(numeric_level)
    root.addHandler(stdout_handler)

    # Add file handler - write to data directory
    log_file = get_data_dir() / "gaze.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)
    root.addHandler(file_handler)
    _log_file_handler = file_handler

    # Set module-specific log levels
    default_module_levels = {
        "uvicorn": "WARNING",
        "uvicorn.access": "WARNING",
        "httpx": "WARNING",
        "aiosqlite": "WARNING",  # Suppress verbose DEBUG logs from aiosqlite
    }
    default_module_levels.update(module_levels)
    
    for module_name, module_level in default_module_levels.items():
        numeric_module_level = getattr(logging, module_level.upper(), logging.WARNING)
        logging.getLogger(module_name).setLevel(numeric_module_level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    if name not in _logger_cache:
        _logger_cache[name] = logging.getLogger(name)
    return _logger_cache[name]


def redact_token(message: str, token: str) -> str:
    """Redact auth token from log messages."""
    if token and token in message:
        return message.replace(token, "[REDACTED]")
    return message
