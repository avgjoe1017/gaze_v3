"""Database module for Gaze Engine."""

from .connection import get_db, init_database

__all__ = ["get_db", "init_database"]
