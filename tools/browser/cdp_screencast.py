"""
CDP Screencast Manager for real-time browser streaming.

This module provides real-time browser frame streaming using Chrome DevTools Protocol.
Uses Page.startScreencast to get continuous frames at configurable quality and frame rate.

Usage:
    from tools.browser.cdp_screencast import CDPScreencast

    async def on_frame(frame_data: str, metadata: dict):
        # frame_data is base64 encoded JPEG
        print(f"Frame received: {len(frame_data)} bytes")

    screencast = CDPScreencast(page, on_frame)
    await screencast.start(quality=80, max_fps=5)
    # ... later
    await screencast.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Type for frame callback - can be sync or async
FrameCallback = Callable[[str, Dict[str, Any]], Union[None, Awaitable[None]]]


class CDPScreencast:
    """
    Manages CDP screencast for real-time frame streaming.

    Uses Page.startScreencast to get continuous frames from the browser.
    Frames are delivered as base64-encoded JPEG images.
    """

    def __init__(
        self,
        page: Any,  # Playwright Page object
        on_frame: FrameCallback,
        thread_id: Optional[str] = None,
    ):
        """
        Initialize CDPScreencast.

        Args:
            page: Playwright Page object
            on_frame: Callback function called with (frame_data_base64, metadata)
            thread_id: Optional thread ID for logging
        """
        self.page = page
        self.on_frame = on_frame
        self.thread_id = thread_id
        self.cdp_session: Optional[Any] = None
        self._running = False
        self._frame_count = 0
        self._start_time: Optional[float] = None
        self._last_frame_time: float = 0
        self._min_frame_interval: float = 0  # Will be set based on max_fps

    @property
    def is_running(self) -> bool:
        """Check if screencast is currently running."""
        return self._running

    @property
    def frame_count(self) -> int:
        """Get number of frames received."""
        return self._frame_count

    @property
    def fps(self) -> float:
        """Get actual frames per second."""
        if not self._start_time or self._frame_count == 0:
            return 0.0
        elapsed = time.time() - self._start_time
        return self._frame_count / elapsed if elapsed > 0 else 0.0

    async def start(
        self,
        quality: int = 80,
        max_width: int = 1280,
        max_height: int = 720,
        max_fps: int = 5,
        format: str = "jpeg",
    ) -> bool:
        """
        Start screencast streaming.

        Args:
            quality: JPEG quality (1-100), lower = smaller size
            max_width: Maximum frame width
            max_height: Maximum frame height
            max_fps: Maximum frames per second (rate limiting)
            format: Image format ("jpeg" or "png")

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning(f"[CDP] Screencast already running for thread {self.thread_id}")
            return False

        try:
            # Create CDP session
            self.cdp_session = await self.page.context.new_cdp_session(self.page)

            # Set up frame rate limiting
            self._min_frame_interval = 1.0 / max_fps if max_fps > 0 else 0
            self._last_frame_time = 0
            self._frame_count = 0
            self._start_time = time.time()

            # Listen for frames
            self.cdp_session.on("Page.screencastFrame", self._handle_frame)

            # Start screencast
            await self.cdp_session.send("Page.startScreencast", {
                "format": format,
                "quality": quality,
                "maxWidth": max_width,
                "maxHeight": max_height,
                "everyNthFrame": 1,  # Get every frame, we'll rate limit ourselves
            })

            self._running = True
            logger.info(f"[CDP] Screencast started for thread {self.thread_id} "
                       f"(quality={quality}, max_fps={max_fps})")
            return True

        except Exception as e:
            logger.error(f"[CDP] Failed to start screencast: {e}")
            self._running = False
            return False

    async def _handle_frame(self, params: Dict[str, Any]) -> None:
        """Handle incoming screencast frame from CDP."""
        if not self._running:
            return

        try:
            session_id = params.get("sessionId")
            frame_data = params.get("data")  # base64 encoded
            metadata = params.get("metadata", {})

            # Acknowledge the frame immediately to prevent blocking
            if self.cdp_session and session_id:
                try:
                    await self.cdp_session.send("Page.screencastFrameAck", {
                        "sessionId": session_id
                    })
                except Exception:
                    pass  # Ignore ack errors

            # Rate limiting
            current_time = time.time()
            if current_time - self._last_frame_time < self._min_frame_interval:
                return  # Skip this frame due to rate limiting

            self._last_frame_time = current_time
            self._frame_count += 1

            # Call the frame callback
            if frame_data and self.on_frame:
                try:
                    result = self.on_frame(frame_data, metadata)
                    # Handle async callback
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.warning(f"[CDP] Frame callback error: {e}")

        except Exception as e:
            logger.error(f"[CDP] Error handling frame: {e}")

    async def stop(self) -> None:
        """Stop screencast streaming."""
        if not self._running:
            return

        self._running = False

        try:
            if self.cdp_session:
                try:
                    await self.cdp_session.send("Page.stopScreencast")
                except Exception:
                    pass  # Ignore errors during stop

                try:
                    await self.cdp_session.detach()
                except Exception:
                    pass

            logger.info(f"[CDP] Screencast stopped for thread {self.thread_id} "
                       f"(frames={self._frame_count}, avg_fps={self.fps:.1f})")

        except Exception as e:
            logger.error(f"[CDP] Error stopping screencast: {e}")
        finally:
            self.cdp_session = None

    async def capture_frame(self) -> Optional[str]:
        """
        Capture a single frame immediately.

        Returns:
            Base64 encoded image data, or None if failed
        """
        try:
            if not self.cdp_session:
                # Create temporary CDP session
                cdp = await self.page.context.new_cdp_session(self.page)
                try:
                    result = await cdp.send("Page.captureScreenshot", {
                        "format": "jpeg",
                        "quality": 80,
                    })
                    return result.get("data")
                finally:
                    await cdp.detach()
            else:
                # Use existing session
                result = await self.cdp_session.send("Page.captureScreenshot", {
                    "format": "jpeg",
                    "quality": 80,
                })
                return result.get("data")

        except Exception as e:
            logger.error(f"[CDP] Failed to capture frame: {e}")
            return None


class ScreencastManager:
    """
    Manages multiple screencast sessions across threads.

    Provides a singleton-style interface for managing CDP screencasts.
    """

    def __init__(self):
        self._screencasts: Dict[str, CDPScreencast] = {}
        self._lock = asyncio.Lock()

    async def start_screencast(
        self,
        thread_id: str,
        page: Any,
        on_frame: FrameCallback,
        **kwargs,
    ) -> bool:
        """
        Start screencast for a thread.

        Args:
            thread_id: Thread/conversation ID
            page: Playwright Page object
            on_frame: Frame callback
            **kwargs: Additional arguments for CDPScreencast.start()

        Returns:
            True if started successfully
        """
        async with self._lock:
            # Stop existing screencast if any
            if thread_id in self._screencasts:
                await self._screencasts[thread_id].stop()

            screencast = CDPScreencast(page, on_frame, thread_id)
            success = await screencast.start(**kwargs)

            if success:
                self._screencasts[thread_id] = screencast

            return success

    async def stop_screencast(self, thread_id: str) -> None:
        """Stop screencast for a thread."""
        async with self._lock:
            if thread_id in self._screencasts:
                await self._screencasts[thread_id].stop()
                del self._screencasts[thread_id]

    async def stop_all(self) -> None:
        """Stop all screencasts."""
        async with self._lock:
            for screencast in self._screencasts.values():
                await screencast.stop()
            self._screencasts.clear()

    def get(self, thread_id: str) -> Optional[CDPScreencast]:
        """Get screencast for a thread."""
        return self._screencasts.get(thread_id)

    def is_active(self, thread_id: str) -> bool:
        """Check if screencast is active for a thread."""
        screencast = self._screencasts.get(thread_id)
        return screencast is not None and screencast.is_running


# Global screencast manager instance
_screencast_manager: Optional[ScreencastManager] = None


def get_screencast_manager() -> ScreencastManager:
    """Get the global screencast manager instance."""
    global _screencast_manager
    if _screencast_manager is None:
        _screencast_manager = ScreencastManager()
    return _screencast_manager
