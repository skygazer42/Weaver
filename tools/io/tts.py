"""
DashScope TTS (Text-to-Speech) using CosyVoice models.
Hard-requires the DashScope SDK and a valid `DASHSCOPE_API_KEY`.
"""

import base64
import logging
import os
import time
from importlib import metadata
from typing import Any, Dict, Optional

import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer

logger = logging.getLogger(__name__)

# Available voices (simplified descriptions kept ASCII for clarity)
AVAILABLE_VOICES = {
    "longanyang": "Longanyang (male, Mandarin)",
    "longxiaochun": "Longxiaochun (female, Mandarin)",
    "longwan": "Longwan (female, warm)",
    "longyue": "Longyue (female, lively)",
    "longfei": "Longfei (male, magnetic)",
    "longjielidou": "Longjielidou (boy)",
    "longshuo": "Longshuo (male, deep)",
    "longshu": "Longshu (female, wise)",
    "loongstella": "Stella (female, English)",
    "loongbella": "Bella (female, English)",
}

DEFAULT_VOICE = "longxiaochun"
DEFAULT_MODEL = "cosyvoice-v3-flash"


class TTSService:
    """Text-to-speech service powered by DashScope."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        if not self.api_key:
            self.enabled = False
            logger.warning("DASHSCOPE_API_KEY not set. TTS service disabled.")
            return

        dashscope.api_key = self.api_key
        self.enabled = True
        self._warn_if_old_sdk()

    def synthesize(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        model: str = DEFAULT_MODEL,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> Dict[str, Any]:
        """Run TTS and return a base64-encoded MP3 payload."""
        if not text or not text.strip():
            raise ValueError("Text cannot be empty.")

        max_length = 2000
        if len(text) > max_length:
            text = text[:max_length] + "..."
            logger.warning("Text truncated to %s characters", max_length)

        if voice not in AVAILABLE_VOICES:
            logger.warning(
                "Requested voice '%s' not in AVAILABLE_VOICES; proceeding anyway.", voice
            )

        audio_data = None
        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                synthesizer = SpeechSynthesizer(model=model, voice=voice)
                audio_data = synthesizer.call(text)
                if audio_data:
                    break
                last_error = RuntimeError("No audio data returned from DashScope.")
            except Exception as exc:  # noqa: PERF203
                last_error = exc
                logger.warning("TTS attempt %s/%s failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(retry_delay)

        if not audio_data:
            raise RuntimeError(f"TTS failed after {max_retries} attempts: {last_error}")

        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        logger.info("TTS success: %s chars -> %s bytes", len(text), len(audio_data))

        return {
            "success": True,
            "audio": audio_base64,
            "format": "mp3",
            "voice": voice,
            "text_length": len(text),
            "error": None,
        }

    def get_available_voices(self) -> Dict[str, str]:
        return AVAILABLE_VOICES.copy()

    @staticmethod
    def _warn_if_old_sdk(min_version: str = "1.24.6") -> None:
        """Log a warning if the installed dashscope SDK is older than recommended."""
        try:
            current = metadata.version("dashscope")
            if tuple(int(x) for x in current.split(".")[:3]) < tuple(
                int(x) for x in min_version.split(".")
            ):
                logger.warning(
                    "dashscope %s detected; TTS works best with >= %s", current, min_version
                )
        except Exception:
            # Version introspection is best-effort only
            pass


# Global TTS service instance (lazy-init)
_tts_service: Optional[TTSService] = None


def get_tts_service(api_key: Optional[str] = None) -> TTSService:
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService(api_key)
    return _tts_service


def init_tts_service(api_key: str) -> TTSService:
    global _tts_service
    _tts_service = TTSService(api_key)
    return _tts_service
