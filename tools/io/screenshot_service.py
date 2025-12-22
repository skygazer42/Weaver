"""
Screenshot Storage and HTTP Service.

This module handles:
- Saving browser screenshots to disk
- Generating accessible URLs
- Cleaning up old screenshots
- Serving screenshots via FastAPI

Usage:
    from tools.io.screenshot_service import ScreenshotService

    service = ScreenshotService()

    # Save a screenshot
    result = await service.save_screenshot(
        image_data=b"...",  # PNG bytes
        action="navigate",
        thread_id="thread_123"
    )
    # result = {"url": "/api/screenshots/...", "filename": "...", "path": "..."}

    # Or save from base64
    result = await service.save_screenshot_base64(
        base64_data="iVBORw0KGgo...",
        action="click",
        thread_id="thread_123"
    )
"""

import asyncio
import base64
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default screenshots directory
DEFAULT_SCREENSHOTS_DIR = "screenshots"

# Screenshot retention period (hours)
SCREENSHOT_RETENTION_HOURS = 24


class ScreenshotService:
    """
    Service for saving and managing browser screenshots.

    Screenshots are saved to disk with unique filenames and can be
    accessed via HTTP endpoint.
    """

    def __init__(
        self,
        screenshots_dir: str = DEFAULT_SCREENSHOTS_DIR,
        base_url: str = "/api/screenshots",
        retention_hours: int = SCREENSHOT_RETENTION_HOURS,
    ):
        """
        Initialize the screenshot service.

        Args:
            screenshots_dir: Directory to save screenshots
            base_url: Base URL path for screenshot access
            retention_hours: How long to keep screenshots (hours)
        """
        self.screenshots_dir = Path(screenshots_dir)
        self.base_url = base_url.rstrip("/")
        self.retention_hours = retention_hours
        self._lock = asyncio.Lock()

        # Ensure directory exists
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[screenshot] Service initialized | Dir: {self.screenshots_dir}")

    def _generate_filename(
        self,
        action: str,
        thread_id: Optional[str] = None,
        extension: str = "png",
    ) -> str:
        """
        Generate a unique filename for a screenshot.

        Format: {thread_id}_{action}_{timestamp}.{ext}
        """
        # Sanitize action name
        safe_action = re.sub(r"[^a-zA-Z0-9_-]", "_", action)[:50]

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Build filename
        parts = []
        if thread_id:
            safe_thread = re.sub(r"[^a-zA-Z0-9_-]", "_", thread_id)[:20]
            parts.append(safe_thread)
        parts.append(safe_action)
        parts.append(timestamp)

        filename = "_".join(parts) + f".{extension}"
        return filename

    async def save_screenshot(
        self,
        image_data: bytes,
        action: str = "screenshot",
        thread_id: Optional[str] = None,
        page_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Save a screenshot to disk.

        Args:
            image_data: Raw image bytes (PNG/JPEG)
            action: Action name that triggered the screenshot
            thread_id: Thread/conversation ID
            page_url: URL of the page being captured
            metadata: Additional metadata to include in result

        Returns:
            Dict with url, filename, path, and metadata
        """
        async with self._lock:
            try:
                # Detect image format
                extension = "png"
                if image_data[:3] == b"\xff\xd8\xff":
                    extension = "jpg"
                elif image_data[:4] == b"\x89PNG":
                    extension = "png"

                # Generate filename and path
                filename = self._generate_filename(action, thread_id, extension)
                filepath = self.screenshots_dir / filename

                # Save to disk
                filepath.write_bytes(image_data)

                # Build result
                url = f"{self.base_url}/{filename}"
                result = {
                    "url": url,
                    "filename": filename,
                    "path": str(filepath),
                    "action": action,
                    "thread_id": thread_id,
                    "page_url": page_url,
                    "timestamp": datetime.now().isoformat(),
                    "size_bytes": len(image_data),
                }

                if metadata:
                    result["metadata"] = metadata

                logger.debug(f"[screenshot] Saved: {filename} ({len(image_data)} bytes)")
                return result

            except Exception as e:
                logger.error(f"[screenshot] Failed to save: {e}")
                return {
                    "url": None,
                    "filename": None,
                    "error": str(e),
                    "action": action,
                    "thread_id": thread_id,
                }

    async def save_screenshot_base64(
        self,
        base64_data: str,
        action: str = "screenshot",
        thread_id: Optional[str] = None,
        page_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Save a base64-encoded screenshot to disk.

        Args:
            base64_data: Base64 encoded image data (with or without data URL prefix)
            action: Action name that triggered the screenshot
            thread_id: Thread/conversation ID
            page_url: URL of the page being captured
            metadata: Additional metadata

        Returns:
            Dict with url, filename, path, and metadata
        """
        try:
            # Strip data URL prefix if present
            if base64_data.startswith("data:"):
                # Format: data:image/png;base64,iVBORw0...
                _, base64_data = base64_data.split(",", 1)

            # Decode base64
            image_data = base64.b64decode(base64_data)

            return await self.save_screenshot(
                image_data=image_data,
                action=action,
                thread_id=thread_id,
                page_url=page_url,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"[screenshot] Failed to decode base64: {e}")
            return {
                "url": None,
                "filename": None,
                "error": str(e),
                "action": action,
                "thread_id": thread_id,
            }

    def get_screenshot_path(self, filename: str) -> Optional[Path]:
        """
        Get the full path for a screenshot filename.

        Args:
            filename: The screenshot filename

        Returns:
            Path object if file exists, None otherwise
        """
        # Sanitize filename to prevent path traversal
        safe_filename = os.path.basename(filename)
        filepath = self.screenshots_dir / safe_filename

        if filepath.exists() and filepath.is_file():
            return filepath
        return None

    async def cleanup_old_screenshots(self) -> int:
        """
        Remove screenshots older than retention period.

        Returns:
            Number of files deleted
        """
        deleted_count = 0
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)

        try:
            for filepath in self.screenshots_dir.iterdir():
                if not filepath.is_file():
                    continue

                # Check file modification time
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                if mtime < cutoff_time:
                    filepath.unlink()
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"[screenshot] Cleanup: deleted {deleted_count} old files")

        except Exception as e:
            logger.error(f"[screenshot] Cleanup error: {e}")

        return deleted_count

    def list_screenshots(
        self,
        thread_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        """
        List available screenshots.

        Args:
            thread_id: Filter by thread ID (if included in filename)
            limit: Maximum number of results

        Returns:
            List of screenshot info dicts
        """
        results = []

        try:
            files = sorted(
                self.screenshots_dir.iterdir(),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for filepath in files[:limit * 2]:  # Extra buffer for filtering
                if not filepath.is_file():
                    continue

                filename = filepath.name

                # Filter by thread_id if specified
                if thread_id and thread_id not in filename:
                    continue

                stat = filepath.stat()
                results.append({
                    "url": f"{self.base_url}/{filename}",
                    "filename": filename,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

                if len(results) >= limit:
                    break

        except Exception as e:
            logger.error(f"[screenshot] List error: {e}")

        return results


# Global singleton instance
_screenshot_service: Optional[ScreenshotService] = None


def get_screenshot_service() -> ScreenshotService:
    """Get or create the global screenshot service instance."""
    global _screenshot_service

    if _screenshot_service is None:
        _screenshot_service = ScreenshotService()

    return _screenshot_service


def init_screenshot_service(
    screenshots_dir: str = DEFAULT_SCREENSHOTS_DIR,
    base_url: str = "/api/screenshots",
) -> ScreenshotService:
    """
    Initialize the global screenshot service with custom settings.

    Args:
        screenshots_dir: Directory for screenshots
        base_url: Base URL for screenshot access

    Returns:
        The initialized ScreenshotService
    """
    global _screenshot_service

    _screenshot_service = ScreenshotService(
        screenshots_dir=screenshots_dir,
        base_url=base_url,
    )

    return _screenshot_service
