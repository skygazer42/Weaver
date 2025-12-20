# API Endpoint Status / 已知问题

Last updated: 2025-12-20

This file tracks API endpoint status and any known issues. (No emoji to avoid Windows console encoding problems.)

## Current Status

| Endpoint | Method | Status | Notes |
|---|---:|---:|---|
| `/` | GET | OK | Health |
| `/health` | GET | OK | Detailed health |
| `/metrics` | GET | OK/404 | 404 unless `ENABLE_PROMETHEUS=true` |
| `/api/runs` | GET | OK | In-memory run metrics |
| `/api/runs/{id}` | GET | OK/404 | 404 when unknown |
| `/api/memory/status` | GET | OK | Memory backend info |
| `/api/mcp/config` | GET/POST | OK | Works even when MCP disabled |
| `/api/tasks/active` | GET | OK | Fixed: no more `stats` NameError |
| `/api/chat/cancel/{id}` | POST | OK | Fixed: `active_streams` defined |
| `/api/chat/cancel-all` | POST | OK | Fixed: `active_streams` defined |
| `/api/interrupt/resume` | POST | 404/200 | 404 if no checkpoint for `thread_id` |
| `/api/asr/status` | GET | OK | Requires `DASHSCOPE_API_KEY` for enabled=true |
| `/api/asr/upload` | POST | OK/503 | Fixed: `filename` NameError; 503 when ASR not configured |
| `/api/tts/status` | GET | OK | Requires `DASHSCOPE_API_KEY` for enabled=true |
| `/api/tts/voices` | GET | OK | Returns supported voice ids |
| `/api/tts/synthesize` | POST | OK/5xx | Upstream DashScope may return no audio; will surface as error |
| `/api/chat` | POST | OK | Model now respects request `model` (fallback to `PRIMARY_MODEL`) |
| `/api/research` | POST | OK | Streaming SSE |
| `/api/support/chat` | POST | Depends | Requires valid LLM credentials + compatible model |

## Fixes Applied (Code)

1) Cancellation endpoints no longer 500
- `main.py`: `active_streams` is now defined as a real global variable.
- `/api/tasks/active` now returns `cancellation_manager.get_stats()`.

2) ASR upload no longer throws `filename is not defined`
- `main.py`: split the comment+assignment line into a real `filename = ...` statement.

3) Interrupt resume is safer
- `main.py`: `/api/interrupt/resume` now returns 404 when no checkpoint exists for the given `thread_id` (instead of 500).

4) Model switching works end-to-end
- `agent/nodes.py`, `agent/agent_factory.py`, `agent/deepsearch.py`, `main.py`: execution now uses `configurable.model` (from request) instead of hardcoding settings.

## Quick Verification Commands

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/tasks/active
curl -X POST http://localhost:8000/api/chat/cancel/test-thread-123
curl -X POST http://localhost:8000/api/chat/cancel-all
curl -X POST http://localhost:8000/api/interrupt/resume \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"nope\",\"payload\":{}}"
```

---

## Pending Issues (DashScope ASR/TTS)

### 5. ASR Upload - Recognition callback error

**Error:**
```
{"success":false,"text":"","error":"ASR exception: Recognition.__init__() missing 1 required positional argument: 'callback'"}
```

**File:** `tools/asr.py:65-70`

**Current Code (Wrong):**
```python
from dashscope.audio.asr import Recognition

recognition = Recognition(
    model='fun-asr-realtime-2025-11-07',
    format=format,
    sample_rate=sample_rate,
    language_hints=language_hints
)
result = recognition.call(file_path)
```

**Problem:**
- `Recognition` is for real-time streaming ASR and requires a `callback` parameter
- For recorded audio file recognition, should use `Transcription` class instead

**Fix - Use Transcription for file recognition:**
```python
from dashscope.audio.asr import Transcription
from http import HTTPStatus
import json

# For local files, first upload or use file_urls
task_response = Transcription.async_call(
    model='fun-asr',
    file_urls=['https://example.com/audio.wav']  # or upload file first
)

# Wait for result
transcribe_response = Transcription.wait(task=task_response.output.task_id)

if transcribe_response.status_code == HTTPStatus.OK:
    result = transcribe_response.output
    # Extract text from result
```

**Alternative - Use Recognition with callback (for streaming):**
```python
from dashscope.audio.asr import Recognition, RecognitionCallback

class MyCallback(RecognitionCallback):
    def on_complete(self):
        pass
    def on_error(self, result):
        pass
    def on_event(self, result):
        # Handle recognition result
        pass

recognition = Recognition(
    model='fun-asr-realtime',
    format='wav',
    sample_rate=16000,
    callback=MyCallback()
)
recognition.start()
recognition.send_audio_frame(audio_bytes)
recognition.stop()
```

**References:**
- [Fun-ASR Recorded Speech Recognition Python SDK](https://help.aliyun.com/zh/model-studio/funauidio-asr-recorded-speech-recognition-python-sdk)
- [Real-time Speech Recognition](https://help.aliyun.com/zh/model-studio/real-time-speech-recognition)

---

### 6. TTS Synthesize - No audio data returned

**Error:**
```
{"detail":"TTS processing error: No audio data returned from DashScope."}
```

**File:** `tools/tts.py:60-64`

**Current Code:**
```python
from dashscope.audio.tts_v2 import SpeechSynthesizer

synthesizer = SpeechSynthesizer(model=model, voice=voice)
audio_data = synthesizer.call(text)

if not audio_data:
    raise RuntimeError("No audio data returned from DashScope.")
```

**Possible Causes:**
1. DashScope SDK version too old (need >= 1.24.6)
2. Model name incorrect or not available
3. API Key quota exhausted or permissions issue
4. Network/API temporary failure

**Fix Options:**

1. **Update SDK version:**
```bash
pip install --upgrade dashscope>=1.24.6
```

2. **Check model availability:**
```python
# Try different models:
# - cosyvoice-v3-flash (recommended)
# - cosyvoice-v2
# - cosyvoice-v1
```

3. **Add error handling and retry:**
```python
import time

def synthesize_with_retry(text, voice, model, max_retries=3):
    for attempt in range(max_retries):
        try:
            synthesizer = SpeechSynthesizer(model=model, voice=voice)
            audio_data = synthesizer.call(text)
            if audio_data:
                return audio_data
        except Exception as e:
            logger.warning(f"TTS attempt {attempt+1} failed: {e}")
            time.sleep(1)
    raise RuntimeError("TTS failed after retries")
```

4. **Verify API Key permissions:**
```bash
# Check if TTS is enabled for your API key at:
# https://dashscope.console.aliyun.com/
```

**References:**
- [CosyVoice Python SDK](https://help.aliyun.com/zh/model-studio/cosyvoice-python-sdk)
- [Text-to-Speech Overview](https://help.aliyun.com/zh/model-studio/text-to-speech)

---

## SDK Version Requirements

| Package | Minimum Version | Current Requirement |
|---------|-----------------|---------------------|
| dashscope | >= 1.24.6 | TTS v2 API support |

Check current version:
```bash
pip show dashscope
```

Upgrade:
```bash
pip install --upgrade dashscope
```

