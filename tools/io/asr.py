"""
DashScope ASR (Automatic Speech Recognition) 语音识别工具

使用阿里云 DashScope 的 fun-asr-realtime 模型进行语音转文字
"""

import logging
import os
import tempfile
from http import HTTPStatus
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from dashscope.audio.asr import Recognition, RecognitionCallback, Transcription

logger = logging.getLogger(__name__)


class _NoOpCallback(RecognitionCallback):
    """Minimal callback to satisfy Recognition constructor."""

    def on_open(self):
        pass

    def on_complete(self):
        pass

    def on_error(self, result):
        pass

    def on_close(self):
        pass

    def on_event(self, result):
        pass


def _is_url(path: str) -> bool:
    try:
        parsed = urlparse(path)
        return parsed.scheme in {"http", "https"}
    except Exception:
        return False


class ASRService:
    """语音识别服务"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 ASR 服务

        Args:
            api_key: DashScope API Key，如果不提供则从环境变量读取
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")

        if self.api_key:
            import dashscope

            dashscope.api_key = self.api_key
            self.enabled = True
        else:
            self.enabled = False

    def recognize_file(
        self,
        file_path: str,
        format: str = "wav",
        sample_rate: int = 16000,
        language_hints: Optional[list] = None,
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
            return {"success": False, "error": "ASR service not available", "text": ""}

        try:
            language_hints = language_hints or ["zh", "en"]

            # Remote files use transcription API; local files fall back to streaming recognition.
            if _is_url(file_path):
                transcribe_resp = Transcription.call(
                    model="fun-asr", file_urls=[file_path], api_key=self.api_key
                )
                if transcribe_resp.status_code == HTTPStatus.OK and transcribe_resp.output:
                    text = self._extract_transcription_text(transcribe_resp.output)
                    return {"success": True, "text": text, "metrics": None, "error": None}
                error_msg = f"ASR failed: {transcribe_resp.message}"
                logger.error(error_msg)
                return {"success": False, "text": "", "error": error_msg}

            callback = _NoOpCallback()
            recognition = Recognition(
                model="fun-asr-realtime-2025-11-07",
                callback=callback,
                format=format,
                sample_rate=sample_rate,
            )

            result = recognition.call(file_path)

            if result.status_code == HTTPStatus.OK:
                text = self._extract_recognition_text(result.get_sentence())

                metrics = {
                    "request_id": recognition.get_last_request_id(),
                    "first_package_delay_ms": recognition.get_first_package_delay(),
                    "last_package_delay_ms": recognition.get_last_package_delay(),
                }

                logger.info(f"ASR success: {text[:50]}... | metrics: {metrics}")

                return {"success": True, "text": text, "metrics": metrics, "error": None}

            error_msg = f"ASR failed: {result.message}"
            logger.error(error_msg)
            return {"success": False, "text": "", "error": error_msg}

        except Exception as e:
            error_msg = f"ASR exception: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "text": "", "error": error_msg}

    def recognize_bytes(
        self,
        audio_data: bytes,
        format: str = "wav",
        sample_rate: int = 16000,
        language_hints: Optional[list] = None,
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
            return {"success": False, "error": "ASR service not available", "text": ""}

        # 将字节数据写入临时文件
        suffix = f".{format}"
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                tmp_file.write(audio_data)
                tmp_path = tmp_file.name

            # 调用文件识别
            result = self.recognize_file(
                tmp_path, format=format, sample_rate=sample_rate, language_hints=language_hints
            )

            return result

        finally:
            # 清理临时文件
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    @staticmethod
    def _extract_recognition_text(sentence) -> str:
        if sentence is None:
            return ""
        if isinstance(sentence, list):
            parts = []
            for item in sentence:
                if isinstance(item, dict):
                    if "text" in item:
                        parts.append(str(item["text"]))
                    elif "sentence" in item:
                        parts.append(str(item["sentence"]))
                    else:
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return " ".join(p for p in parts if p)
        if isinstance(sentence, dict):
            return str(sentence.get("text") or sentence.get("sentence") or "")
        return str(sentence)

    @staticmethod
    def _extract_transcription_text(output) -> str:
        if output is None:
            return ""
        if isinstance(output, dict):
            if "text" in output:
                return str(output["text"])
            if "result" in output and isinstance(output["result"], dict):
                return str(output["result"].get("text", ""))
            if "sentences" in output and isinstance(output["sentences"], list):
                return " ".join(
                    str(s.get("text", "")) for s in output["sentences"] if isinstance(s, dict)
                )
        return str(output)


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
