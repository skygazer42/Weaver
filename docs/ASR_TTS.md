# ASR / TTS（DashScope，可选）

Weaver 支持可选的语音能力：

- ASR：语音转文字
- TTS：文字转语音

实现位置：`tools/asr.py`、`tools/tts.py`；API 位于 `main.py` 的 `/api/asr/*`、`/api/tts/*`。

## 1. 前置条件

- `.env` 配置 `DASHSCOPE_API_KEY`
- Python 依赖建议：`dashscope>=1.24.6`（见 `requirements.txt`）

## 2. ASR

### API

- `GET /api/asr/status`
- `POST /api/asr/recognize`（base64 音频）
- `POST /api/asr/upload`（上传音频文件）

### 实现说明（tools/asr.py）

- 如果传入的是 `http/https` URL：走 `Transcription.call(...)`（录音文件识别接口）
- 如果是本地文件路径：走 `Recognition(...).call(file_path)`（流式识别接口，使用 no-op callback 规避 callback 必填）

注意：DashScope 的录音文件识别通常更推荐“上传后用 URL”，因此在生产场景建议统一走 URL 路线。

## 3. TTS

### API

- `GET /api/tts/status`
- `GET /api/tts/voices`
- `POST /api/tts/synthesize`

### 实现说明（tools/tts.py）

- 默认模型：`cosyvoice-v3-flash`
- 默认 voice：`longxiaochun`
- 内置重试：`max_retries` / `retry_delay`（默认 3 次 / 1 秒）
- 如果 DashScope 返回空音频，会在重试耗尽后抛错并返回 5xx

