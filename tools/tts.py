"""
DashScope TTS (Text-to-Speech) 文字转语音服务

使用阿里云 DashScope 的 CosyVoice 模型进行语音合成
"""

import os
import logging
from typing import Optional, Dict, Any
import base64

logger = logging.getLogger(__name__)

try:
    from dashscope.audio.tts_v2 import SpeechSynthesizer
    DASHSCOPE_TTS_AVAILABLE = True
except ImportError:
    DASHSCOPE_TTS_AVAILABLE = False
    logger.warning("dashscope TTS not available. TTS features will be disabled.")


# 可用的声音列表
AVAILABLE_VOICES = {
    # 中文声音
    "longanyang": "龙昂扬 (男声，普通话)",
    "longxiaochun": "龙小淳 (女声，普通话)",
    "longwan": "龙婉 (女声，温柔)",
    "longyue": "龙悦 (女声，活泼)",
    "longfei": "龙飞 (男声，磁性)",
    "longjielidou": "龙杰力豆 (男童声)",
    "longshuo": "龙硕 (男声，沉稳)",
    "longshu": "龙姝 (女声，知性)",
    # 英文声音
    "loongstella": "Stella (女声，英文)",
    "loongbella": "Bella (女声，英文)",
}

DEFAULT_VOICE = "longxiaochun"
DEFAULT_MODEL = "cosyvoice-v3-flash"


class TTSService:
    """文字转语音服务"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 TTS 服务

        Args:
            api_key: DashScope API Key
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")

        if self.api_key and DASHSCOPE_TTS_AVAILABLE:
            import dashscope
            dashscope.api_key = self.api_key
            self.enabled = True
        else:
            self.enabled = False
            if not DASHSCOPE_TTS_AVAILABLE:
                logger.warning("DashScope TTS package not available")
            elif not self.api_key:
                logger.warning("DashScope API key not configured")

    def synthesize(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        model: str = DEFAULT_MODEL
    ) -> Dict[str, Any]:
        """
        合成语音

        Args:
            text: 要转换的文字
            voice: 声音ID
            model: 模型名称

        Returns:
            包含音频数据的字典
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "TTS service not available",
                "audio": None
            }

        if not text or not text.strip():
            return {
                "success": False,
                "error": "Text cannot be empty",
                "audio": None
            }

        # 限制文本长度（避免过长的请求）
        max_length = 2000
        if len(text) > max_length:
            text = text[:max_length] + "..."
            logger.warning(f"Text truncated to {max_length} characters")

        try:
            synthesizer = SpeechSynthesizer(model=model, voice=voice)
            audio_data = synthesizer.call(text)

            if audio_data:
                # 转换为 Base64
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')

                logger.info(f"TTS success: {len(text)} chars -> {len(audio_data)} bytes")

                return {
                    "success": True,
                    "audio": audio_base64,
                    "format": "mp3",
                    "voice": voice,
                    "text_length": len(text),
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "error": "No audio data returned",
                    "audio": None
                }

        except Exception as e:
            error_msg = f"TTS synthesis error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "audio": None
            }

    def get_available_voices(self) -> Dict[str, str]:
        """获取可用的声音列表"""
        return AVAILABLE_VOICES.copy()


# 全局 TTS 服务实例
_tts_service: Optional[TTSService] = None


def get_tts_service(api_key: Optional[str] = None) -> TTSService:
    """获取 TTS 服务单例"""
    global _tts_service

    if _tts_service is None:
        _tts_service = TTSService(api_key)

    return _tts_service


def init_tts_service(api_key: str) -> TTSService:
    """初始化 TTS 服务"""
    global _tts_service
    _tts_service = TTSService(api_key)
    return _tts_service
