"""Logs endpoints."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..middleware.auth import verify_token
from ..utils.logging import get_logger
from ..utils.paths import get_data_dir

logger = get_logger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])


class LogEntry(BaseModel):
    """Single log entry."""

    line: str
    line_number: int


class LogsResponse(BaseModel):
    """Logs response."""

    entries: list[LogEntry]
    total_lines: int
    file_path: str


@router.get("", response_model=LogsResponse)
async def get_logs(
    lines: int = Query(100, ge=1, le=10000, description="Number of lines to retrieve"),
    tail: bool = Query(True, description="If true, get last N lines; if false, get first N lines"),
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = Query(
        None, description="Filter by log level"
    ),
    redact_paths: bool = Query(False, description="Redact file paths and filenames for privacy"),
    _token: str = Depends(verify_token),
) -> LogsResponse:
    """Get log entries from the log file."""
    log_file = get_data_dir() / "gaze.log"

    entries: list[LogEntry] = []
    total_lines = 0

    if not log_file.exists():
        return LogsResponse(
            entries=[],
            total_lines=0,
            file_path=str(log_file),
        )

    try:
        # Read all lines first to get total count
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            total_lines = len(all_lines)

        # Get requested lines
        if tail:
            # Last N lines
            selected_lines = all_lines[-lines:]
        else:
            # First N lines
            selected_lines = all_lines[:lines]

        # Filter by level if specified
        if level:
            selected_lines = [
                line for line in selected_lines if f"| {level:8s} |" in line or f"| {level.upper():8s} |" in line
            ]

        # Redact paths if requested
        if redact_paths:
            import re
            # Pattern to match file paths (Windows and Unix)
            path_pattern = re.compile(
                r'(?:[A-Za-z]:)?(?:[/\\][^\s<>"|:]+)+|'  # Windows/Unix paths
                r'[A-Za-z]:\\[^<>"|:\s]+'  # Windows drive paths
            )
            selected_lines = [
                path_pattern.sub("[REDACTED_PATH]", line) for line in selected_lines
            ]
        
        # Convert to LogEntry objects
        start_line = total_lines - len(selected_lines) if tail else 0
        entries = [
            LogEntry(line=line.rstrip("\n"), line_number=start_line + i + 1)
            for i, line in enumerate(selected_lines)
        ]

    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        return LogsResponse(
            entries=[],
            total_lines=0,
            file_path=str(log_file),
        )

    return LogsResponse(
        entries=entries,
        total_lines=total_lines,
        file_path=str(log_file),
    )
