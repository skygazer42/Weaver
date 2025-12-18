"""
DashScope ASR (Automatic Speech Recognition) 语音识别工具

使用阿里云 DashScope 的 fun-asr-realtime 模型进行语音转文字
"""

import os
import tempfile
import logging
from typing import Optional, Dict, Any
from http import HTTPStatus

logger = logging.getLogger(__name__)

# 尝试导入 dashscope，如果没有安装则跳过
try:
    from dashscope.audio.asr import Recognition
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    logger.warning("dashscope package not installed. ASR features will be disabled.")


class ASRService:
    """语音识别服务"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 ASR 服务

        Args:
            api_key: DashScope API Key，如果不提供则从环境变量读取
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")

        if self.api_key and DASHSCOPE_AVAILABLE:
            import dashscope
            dashscope.api_key = self.api_key
            self.enabled = True
        else:
            self.enabled = False
            if not DASHSCOPE_AVAILABLE:
                logger.warning("DashScope package not available")
            elif not self.api_key:
                logger.warning("DashScope API key not configured")

    def recognize_file(
        self,
        file_path: str,
        format: str = "wav",
        sample_rate: int = 16000,
        language_hints: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        识别音频文件

        Args:
            file_path: 音频文件路径
            format: 音频格式 (wav, mp3, pcm, etc.)
            sample_rate: 采样率
            language_hints: 语言提示 ['zh', 'en']

        Returns:
            识别结果字典
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "ASR service not available",
                "text": ""
            }

        if not DASHSCOPE_AVAILABLE:
            return {
                "success": False,
                "error": "dashscope package not installed",
                "text": ""
            }

        try:
            language_hints = language_hints or ['zh', 'en']

            recognition = Recognition(
                model='fun-asr-realtime-2025-11-07',
                format=format,
                sample_rate=sample_rate,
                language_hints=language_hints,
                callback=None
            )

            result = recognition.call(file_path)

            if result.status_code == HTTPStatus.OK:
                text = result.get_sentence() or ""

                # 获取性能指标
                metrics = {
                    "request_id": recognition.get_last_request_id(),
                    "first_package_delay_ms": recognition.get_first_package_delay(),
                    "last_package_delay_ms": recognition.get_last_package_delay(),
                }

                logger.info(f"ASR success: {text[:50]}... | metrics: {metrics}")

                return {
                    "success": True,
                    "text": text,
                    "metrics": metrics,
                    "error": None
                }
            else:
                error_msg = f"ASR failed: {result.message}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "text": "",
                    "error": error_msg
                }

        except Exception as e:
            error_msg = f"ASR exception: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "text": "",
                "error": error_msg
            }

    def recognize_bytes(
        self,
        audio_data: bytes,
        format: str = "wav",
        sample_rate: int = 16000,
        language_hints: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        识别音频字节数据

        Args:
            audio_data: 音频字节数据
            format: 音频格式
            sample_rate: 采样率
            language_hints: 语言提示

        Returns:
            识别结果字典
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "ASR service not available",
                "text": ""
            }

        # 将字节数据写入临时文件
        suffix = f".{format}"
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                tmp_file.write(audio_data)
                tmp_path = tmp_file.name

            # 调用文件识别
            result = self.recognize_file(
                tmp_path,
                format=format,
                sample_rate=sample_rate,
                language_hints=language_hints
            )

            return result

        finally:
            # 清理临时文件
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass


# 全局 ASR 服务实例
_asr_service: Optional[ASRService] = None


def get_asr_service(api_key: Optional[str] = None) -> ASRService:
    """获取 ASR 服务单例"""
    global _asr_service

    if _asr_service is None:
        _asr_service = ASRService(api_key)

    return _asr_service


def init_asr_service(api_key: str) -> ASRService:
    """初始化 ASR 服务"""
    global _asr_service
    _asr_service = ASRService(api_key)
    return _asr_service
