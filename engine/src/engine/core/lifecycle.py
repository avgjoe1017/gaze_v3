"""Engine lifecycle management."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger
from ..utils.paths import get_lockfile_path

logger = get_logger(__name__)


def check_ffmpeg_available() -> tuple[bool, str | None]:
    """Check if FFmpeg is available in PATH.

    Returns:
        Tuple of (is_available, version_string or None)
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        logger.warning("FFmpeg not found in PATH")
        return False, None

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Extract version from first line, e.g., "ffmpeg version 6.0 ..."
        version_line = result.stdout.split("\n")[0] if result.stdout else ""
        version = version_line.replace("ffmpeg version ", "").split(" ")[0] if version_line else "unknown"
        logger.info(f"FFmpeg found: {version} at {ffmpeg_path}")
        return True, version
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"FFmpeg check failed: {e}")
        return False, None


def check_ffprobe_available() -> tuple[bool, str | None]:
    """Check if FFprobe is available in PATH.

    Returns:
        Tuple of (is_available, version_string or None)
    """
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        logger.warning("FFprobe not found in PATH")
        return False, None

    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        version_line = result.stdout.split("\n")[0] if result.stdout else ""
        version = version_line.replace("ffprobe version ", "").split(" ")[0] if version_line else "unknown"
        logger.info(f"FFprobe found: {version} at {ffprobe_path}")
        return True, version
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"FFprobe check failed: {e}")
        return False, None


# Global state for dependency checks (set on startup)
_ffmpeg_available: bool = False
_ffmpeg_version: str | None = None
_ffprobe_available: bool = False
_ffprobe_version: str | None = None
_gpu_available: bool = False
_gpu_name: str | None = None
_gpu_memory_mb: int | None = None


def check_gpu_available() -> tuple[bool, str | None, int | None]:
    """Check if CUDA GPU is available for ML acceleration.

    Returns:
        Tuple of (is_available, gpu_name or None, memory_mb or None)
    """
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            # Get memory in MB
            props = torch.cuda.get_device_properties(0)
            memory_mb = props.total_memory // (1024 * 1024)
            logger.info(f"GPU found: {gpu_name} with {memory_mb}MB memory")
            return True, gpu_name, memory_mb
        else:
            logger.info("CUDA not available, using CPU for ML inference")
            return False, None, None
    except ImportError:
        logger.debug("PyTorch not installed, GPU check skipped")
        return False, None, None
    except Exception as e:
        logger.warning(f"GPU check failed: {e}")
        return False, None, None


def get_ffmpeg_status() -> dict[str, Any]:
    """Get FFmpeg/FFprobe availability status."""
    return {
        "ffmpeg_available": _ffmpeg_available,
        "ffmpeg_version": _ffmpeg_version,
        "ffprobe_available": _ffprobe_available,
        "ffprobe_version": _ffprobe_version,
    }


def get_gpu_status() -> dict[str, Any]:
    """Get GPU availability status."""
    return {
        "gpu_available": _gpu_available,
        "gpu_name": _gpu_name,
        "gpu_memory_mb": _gpu_memory_mb,
    }


async def repair_consistency() -> dict[str, int]:
    """Repair database consistency after crash or unclean shutdown.

    This function:
    1. Resets videos stuck in intermediate states (processing) back to QUEUED
    2. Cleans up orphaned temporary files
    3. Removes stale job records

    Returns:
        Dict with counts of repaired items
    """
    from ..db.connection import get_db
    from ..utils.paths import get_temp_dir, get_thumbnails_dir, get_faiss_dir

    stats = {
        "videos_reset": 0,
        "jobs_cleaned": 0,
        "temp_files_removed": 0,
    }

    # Processing states that indicate an interrupted operation
    PROCESSING_STATES = [
        "EXTRACTING_AUDIO",
        "TRANSCRIBING",
        "EXTRACTING_FRAMES",
        "EMBEDDING",
        "DETECTING",
    ]

    try:
        async for db in get_db():
            # 1. Find videos stuck in processing states and reset to QUEUED
            cursor = await db.execute(
                f"""
                SELECT video_id, status, path
                FROM videos
                WHERE status IN ({",".join("?" * len(PROCESSING_STATES))})
                """,
                PROCESSING_STATES,
            )
            stuck_videos = await cursor.fetchall()

            for video in stuck_videos:
                video_id = video["video_id"]
                status = video["status"]
                logger.info(
                    f"Resetting stuck video {video_id} from {status} to QUEUED"
                )
                await db.execute(
                    """
                    UPDATE videos
                    SET status = 'QUEUED',
                        progress = 0.0,
                        error_code = NULL,
                        error_message = NULL
                    WHERE video_id = ?
                    """,
                    (video_id,),
                )
                stats["videos_reset"] += 1

            # 2. Clean up any jobs that were marked as 'running' or 'processing'
            cursor = await db.execute(
                """
                SELECT COUNT(*) as count FROM jobs
                WHERE status IN ('running', 'processing')
                """
            )
            row = await cursor.fetchone()
            stale_jobs = row["count"] if row else 0

            if stale_jobs > 0:
                await db.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed',
                        error = 'Interrupted by crash or shutdown'
                    WHERE status IN ('running', 'processing')
                    """
                )
                stats["jobs_cleaned"] = stale_jobs
                logger.info(f"Cleaned {stale_jobs} stale job records")

            await db.commit()

        # 3. Clean up temp directory (audio extraction files, etc.)
        temp_dir = get_temp_dir()
        if temp_dir.exists():
            for temp_file in temp_dir.iterdir():
                if temp_file.is_file():
                    try:
                        temp_file.unlink()
                        stats["temp_files_removed"] += 1
                    except Exception as e:
                        logger.warning(f"Failed to remove temp file {temp_file}: {e}")

            if stats["temp_files_removed"] > 0:
                logger.info(f"Removed {stats['temp_files_removed']} temp files")

    except Exception as e:
        logger.error(f"Error during consistency repair: {e}")

    if stats["videos_reset"] > 0 or stats["jobs_cleaned"] > 0:
        logger.info(
            f"Consistency repair complete: {stats['videos_reset']} videos reset, "
            f"{stats['jobs_cleaned']} jobs cleaned, "
            f"{stats['temp_files_removed']} temp files removed"
        )
    else:
        logger.debug("Consistency check passed - no repairs needed")

    return stats


def pid_exists(pid: int) -> bool:
    """Check if a process with the given PID exists."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class LifecycleManager:
    """Manages engine lifecycle, lockfile, and parent process monitoring."""

    def __init__(self, engine_uuid: str, data_dir: Path):
        self.engine_uuid = engine_uuid
        self.data_dir = data_dir
        self.lockfile_path = get_lockfile_path()
        self.parent_pid = os.environ.get("GAZE_PARENT_PID")
        self._parent_monitor_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()

    async def startup(self) -> None:
        """Perform startup tasks."""
        global _ffmpeg_available, _ffmpeg_version, _ffprobe_available, _ffprobe_version
        global _gpu_available, _gpu_name, _gpu_memory_mb

        # Check external dependencies
        _ffmpeg_available, _ffmpeg_version = check_ffmpeg_available()
        _ffprobe_available, _ffprobe_version = check_ffprobe_available()

        if not _ffmpeg_available or not _ffprobe_available:
            logger.warning(
                "FFmpeg/FFprobe not fully available. "
                "Video indexing will not work until FFmpeg is installed."
            )

        # Check GPU availability
        _gpu_available, _gpu_name, _gpu_memory_mb = check_gpu_available()

        # Clean up stale lockfile from previous crashed instance
        await self._cleanup_stale_lockfile()

        # Write lockfile
        await self._write_lockfile()

        # Start parent monitoring if we have a parent PID
        if self.parent_pid:
            self._parent_monitor_task = asyncio.create_task(
                self._monitor_parent(int(self.parent_pid))
            )
            logger.info(f"Monitoring parent process {self.parent_pid}")

    async def shutdown(self) -> None:
        """Perform shutdown tasks."""
        self._shutdown_event.set()

        # Cancel parent monitor
        if self._parent_monitor_task:
            self._parent_monitor_task.cancel()
            try:
                await self._parent_monitor_task
            except asyncio.CancelledError:
                pass

        # Remove lockfile
        await self._remove_lockfile()

    async def _cleanup_stale_lockfile(self) -> None:
        """Clean up stale lockfile from a crashed previous instance.

        Checks if a lockfile exists and whether the process it references
        is still alive. If the process is dead, removes the stale lockfile.
        If the process is alive, logs a warning (another instance running).
        """
        if not self.lockfile_path.exists():
            return

        try:
            lockfile_content = self.lockfile_path.read_text()
            lockfile_data = json.loads(lockfile_content)
            old_pid = lockfile_data.get("engine_pid")

            if old_pid is None:
                # Malformed lockfile, remove it
                logger.warning("Found malformed lockfile (no PID), removing")
                self.lockfile_path.unlink()
                return

            if pid_exists(old_pid):
                # Another instance is actually running
                logger.warning(
                    f"Another engine instance (PID {old_pid}) appears to be running. "
                    "If this is incorrect, manually delete the lockfile and restart."
                )
                # Don't exit - let the port conflict handling deal with it
                # The new instance will get a different port
                return

            # Old process is dead - stale lockfile
            logger.info(
                f"Found stale lockfile from dead process (PID {old_pid}), removing"
            )
            self.lockfile_path.unlink()

        except json.JSONDecodeError:
            # Corrupted lockfile, remove it
            logger.warning("Found corrupted lockfile, removing")
            self.lockfile_path.unlink()
        except Exception as e:
            logger.warning(f"Error checking stale lockfile: {e}")
            # Try to remove it anyway
            try:
                self.lockfile_path.unlink()
            except Exception:
                pass

    async def _write_lockfile(self) -> None:
        """Write the engine lockfile."""
        lockfile_data = {
            "port": int(os.environ.get("GAZE_PORT", "48100")),
            "token": os.environ.get("GAZE_AUTH_TOKEN", ""),
            "engine_uuid": self.engine_uuid,
            "engine_pid": os.getpid(),
            "parent_pid": int(self.parent_pid) if self.parent_pid else None,
            "created_at_ms": int(datetime.now().timestamp() * 1000),
        }

        self.lockfile_path.parent.mkdir(parents=True, exist_ok=True)
        self.lockfile_path.write_text(json.dumps(lockfile_data, indent=2))

        # Set restrictive permissions on Unix
        if sys.platform != "win32":
            os.chmod(self.lockfile_path, 0o600)

        logger.info(f"Wrote lockfile to {self.lockfile_path}")

    async def _remove_lockfile(self) -> None:
        """Remove the engine lockfile."""
        try:
            if self.lockfile_path.exists():
                self.lockfile_path.unlink()
                logger.info("Removed lockfile")
        except Exception as e:
            logger.warning(f"Failed to remove lockfile: {e}")

    async def _monitor_parent(self, parent_pid: int) -> None:
        """Monitor parent process and shutdown if it dies."""
        consecutive_failures = 0
        max_failures = 3

        while not self._shutdown_event.is_set():
            await asyncio.sleep(10)

            if not pid_exists(parent_pid):
                consecutive_failures += 1
                logger.warning(
                    f"Parent process {parent_pid} not found "
                    f"({consecutive_failures}/{max_failures})"
                )
            else:
                consecutive_failures = 0

            if consecutive_failures >= max_failures:
                logger.warning("Parent process dead, initiating shutdown")
                await self.graceful_shutdown()
                break

    async def graceful_shutdown(self) -> None:
        """Initiate graceful shutdown."""
        logger.info("Graceful shutdown initiated")
        await self.shutdown()
        # Give a moment for cleanup
        await asyncio.sleep(0.5)
        sys.exit(0)
