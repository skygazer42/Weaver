"""
DashScope TTS (Text-to-Speech) using CosyVoice models.
Hard-requires the DashScope SDK and a valid `DASHSCOPE_API_KEY`.
"""

import base64
import logging
import os
from typing import Optional, Dict, Any

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
            raise ValueError("DASHSCOPE_API_KEY is required for TTS.")

        dashscope.api_key = self.api_key
        self.enabled = True

    def synthesize(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        model: str = DEFAULT_MODEL
    ) -> Dict[str, Any]:
        """Run TTS and return a base64-encoded MP3 payload."""
        if not text or not text.strip():
            raise ValueError("Text cannot be empty.")

        max_length = 2000
        if len(text) > max_length:
            text = text[:max_length] + "..."
            logger.warning("Text truncated to %s characters", max_length)

        synthesizer = SpeechSynthesizer(model=model, voice=voice)
        audio_data = synthesizer.call(text)

        if not audio_data:
            raise RuntimeError("No audio data returned from DashScope.")

        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        logger.info("TTS success: %s chars -> %s bytes", len(text), len(audio_data))

        return {
            "success": True,
            "audio": audio_base64,
            "format": "mp3",
            "voice": voice,
            "text_length": len(text),
            "error": None
        }

    def get_available_voices(self) -> Dict[str, str]:
        return AVAILABLE_VOICES.copy()


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
