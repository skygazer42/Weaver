"""
Daytona sandbox client (lightweight stub).

Provides a minimal interface to create/stop a Daytona sandbox and return
connection info (VNC/HTTP endpoints). Intended to be expanded with real API
calls; currently implements a safe no-op when config is missing.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Dict

import requests
from langchain.tools import tool

from common.config import settings
from agent.core.events import get_emitter_sync, ToolEventType


def _emit(thread_id: str, event_type: ToolEventType, data: Dict):
    try:
        emitter = get_emitter_sync(thread_id)
        coro = emitter.emit(event_type, data)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)
    except Exception:
        pass


def _daytona_cfg():
    # Collect config with env overrides
    key = os.getenv("DAYTONA_API_KEY", "") or getattr(settings, "daytona_api_key", "")
    url = getattr(settings, "daytona_server_url", "https://app.daytona.io/api")
    target = getattr(settings, "daytona_target", "us")
    image = getattr(settings, "daytona_image_name", "whitezxj/sandbox:0.1.0")
    entrypoint = getattr(settings, "daytona_entrypoint", "/usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf")
    vnc_pwd = getattr(settings, "daytona_vnc_password", "123456")
    return key, url, target, image, entrypoint, vnc_pwd

# Track active sandbox ids (best-effort), grouped by thread_id for lifecycle cleanup
_ACTIVE_SANDBOX_IDS = set()
_ACTIVE_BY_THREAD = {}


@tool
def daytona_create(thread_id: str = "default") -> Dict[str, str]:
    """
    Create a Daytona sandbox and return endpoints (VNC/HTTP). Returns stub when not configured.
    """
    key, base_url, target, image, entrypoint, vnc_pwd = _daytona_cfg()

    _emit(thread_id, ToolEventType.TOOL_START, {"tool": "daytona_create", "args": {"target": target, "image": image}})

    if not key:
        msg = "Daytona API key not configured; returning placeholder sandbox."
        _emit(thread_id, ToolEventType.TOOL_ERROR, {"tool": "daytona_create", "error": msg})
        return {"status": "not_configured", "message": msg}

    sandbox_id = str(uuid.uuid4())
    try:
        resp = requests.post(
            f"{base_url}/sandboxes",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "target": target,
                "image": image,
                "entrypoint": entrypoint,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        sandbox_id = data.get("id", sandbox_id)
        vnc = data.get("vnc_url") or data.get("vnc") or ""
        http = data.get("http_url") or data.get("http") or ""
        payload = {
            "status": "created",
            "sandbox_id": sandbox_id,
            "vnc_url": vnc,
            "http_url": http,
            "password": vnc_pwd,
        }
        _ACTIVE_SANDBOX_IDS.add(sandbox_id)
        _ACTIVE_BY_THREAD.setdefault(thread_id, set()).add(sandbox_id)
        _emit(thread_id, ToolEventType.TOOL_RESULT, {"tool": "daytona_create", "result": payload, "success": True})
        return payload
    except Exception as e:
        msg = f"Daytona create failed: {e}"
        _emit(thread_id, ToolEventType.TOOL_ERROR, {"tool": "daytona_create", "error": msg})
        return {"status": "error", "message": msg}


@tool
def daytona_stop(sandbox_id: str, thread_id: str = "default") -> Dict[str, str]:
    """Stop a Daytona sandbox by id."""
    key, base_url, *_ = _daytona_cfg()
    _emit(thread_id, ToolEventType.TOOL_START, {"tool": "daytona_stop", "args": {"sandbox_id": sandbox_id}})
    if not key:
        msg = "Daytona API key not configured; nothing to stop."
        _emit(thread_id, ToolEventType.TOOL_ERROR, {"tool": "daytona_stop", "error": msg})
        return {"status": "not_configured", "message": msg}

    try:
        resp = requests.delete(
            f"{base_url}/sandboxes/{sandbox_id}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if resp.status_code in (200, 202, 204):
            payload = {"status": "stopped", "sandbox_id": sandbox_id}
            _ACTIVE_SANDBOX_IDS.discard(sandbox_id)
            for tids in _ACTIVE_BY_THREAD.values():
                tids.discard(sandbox_id)
            _emit(thread_id, ToolEventType.TOOL_RESULT, {"tool": "daytona_stop", "result": payload, "success": True})
            return payload
        msg = f"Stop failed: {resp.status_code} {resp.text}"
        _emit(thread_id, ToolEventType.TOOL_ERROR, {"tool": "daytona_stop", "error": msg})
        return {"status": "error", "message": msg}
    except Exception as e:
        msg = f"Daytona stop failed: {e}"
        _emit(thread_id, ToolEventType.TOOL_ERROR, {"tool": "daytona_stop", "error": msg})
        return {"status": "error", "message": msg}


def daytona_stop_all(thread_id: str = "default") -> Dict[str, str]:
    key, base_url, *_ = _daytona_cfg()
    if not key:
        return {"status": "not_configured", "message": "Daytona API key not configured"}
    stopped = []
    targets = (
        list(_ACTIVE_BY_THREAD.get(thread_id, []))
        if thread_id and thread_id in _ACTIVE_BY_THREAD
        else list(_ACTIVE_SANDBOX_IDS)
    )
    if hasattr(daytona_stop, "invoke"):
        stop_callable = lambda sid: daytona_stop.invoke({"sandbox_id": sid, "thread_id": thread_id})
    elif hasattr(daytona_stop, "run"):
        stop_callable = lambda sid: daytona_stop.run({"sandbox_id": sid, "thread_id": thread_id})
    else:
        stop_callable = lambda sid: daytona_stop(sid, thread_id=thread_id)
    for sid in targets:
        try:
            stop_callable(sid)
        finally:
            stopped.append(sid)
    for sid in stopped:
        _ACTIVE_SANDBOX_IDS.discard(sid)
    if thread_id in _ACTIVE_BY_THREAD:
        _ACTIVE_BY_THREAD.pop(thread_id, None)
    return {"status": "stopped_all", "count": len(stopped), "sandbox_ids": stopped}
