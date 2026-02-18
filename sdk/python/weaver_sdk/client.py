from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .sse import parse_sse_frame
from .types import StreamEvent


@dataclass(frozen=True)
class WeaverApiError(RuntimeError):
    status: int
    path: str
    body_text: str

    def __str__(self) -> str:
        suffix = f": {self.body_text}" if self.body_text else ""
        return f"Weaver API request failed ({self.status}) {self.path}{suffix}"


def _normalize_base_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "http://127.0.0.1:8001"
    return text.rstrip("/")


def _encode_path_param(value: str) -> str:
    return quote(str(value or ""), safe="")


class WeaverClient:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8001",
        headers: dict[str, str] | None = None,
        timeout_s: float = 60.0,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.headers = headers or {}
        self.timeout_s = float(timeout_s)
        self._http = http or httpx.Client(timeout=self.timeout_s)
        self.last_thread_id: str | None = None

    def _url(self, path: str) -> str:
        p = path if str(path).startswith("/") else f"/{path}"
        return f"{self.base_url}{p}"

    def request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        merged_headers = {"Accept": "application/json", **self.headers, **(headers or {})}
        resp = self._http.request(
            method=method,
            url=self._url(path),
            headers=merged_headers,
            params=params,
            json=json_body,
        )

        body_text = resp.text or ""
        if resp.status_code < 200 or resp.status_code >= 300:
            raise WeaverApiError(status=resp.status_code, path=path, body_text=body_text)

        if not body_text.strip():
            return None

        try:
            return resp.json()
        except Exception:
            return body_text

    def cancel_chat(self, thread_id: str) -> Any:
        safe_id = _encode_path_param(thread_id)
        return self.request_json(f"/api/chat/cancel/{safe_id}", method="POST")

    def cancel_all_chats(self) -> Any:
        return self.request_json("/api/chat/cancel-all", method="POST")

    def chat_sse(self, payload: dict[str, Any]) -> Iterator[StreamEvent]:
        """
        Start a chat request and yield StreamEvent items parsed from SSE frames.

        The server typically emits JSON envelope objects: {"type": "...", "data": {...}}.
        This method yields that envelope when present, otherwise falls back to
        {"type": <event>, "data": <parsed data>}.
        """
        merged_headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            **self.headers,
        }

        with self._http.stream(
            "POST",
            self._url("/api/chat/sse"),
            headers=merged_headers,
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ) as resp:
            body_text = ""
            if resp.status_code < 200 or resp.status_code >= 300:
                try:
                    body_text = resp.read().decode("utf-8", errors="ignore")
                except Exception:
                    body_text = ""
                raise WeaverApiError(status=resp.status_code, path="/api/chat/sse", body_text=body_text)

            self.last_thread_id = (
                resp.headers.get("X-Thread-ID")
                or resp.headers.get("x-thread-id")
                or None
            )

            buffer = ""
            for chunk in resp.iter_bytes():
                try:
                    buffer += chunk.decode("utf-8", errors="ignore")
                except Exception:
                    continue

                buffer = buffer.replace("\r\n", "\n")
                frames = buffer.split("\n\n")
                buffer = frames.pop() or ""

                for frame in frames:
                    parsed = parse_sse_frame(frame)
                    if not parsed:
                        continue

                    data = parsed.get("data")
                    if isinstance(data, dict) and "type" in data and "data" in data:
                        yield data  # type: ignore[misc]
                        continue

                    event_name = parsed.get("event")
                    if isinstance(event_name, str) and event_name:
                        yield {"type": event_name, "data": data}

            tail = buffer.strip()
            if tail:
                parsed = parse_sse_frame(tail)
                if parsed:
                    data = parsed.get("data")
                    if isinstance(data, dict) and "type" in data and "data" in data:
                        yield data  # type: ignore[misc]
                    else:
                        event_name = parsed.get("event")
                        if isinstance(event_name, str) and event_name:
                            yield {"type": event_name, "data": data}

    def research_stream(self, query: str) -> Iterator[StreamEvent]:
        """
        Stream research progress events (legacy `0:{...}\\n` protocol).
        """
        merged_headers = {"Accept": "text/event-stream", **self.headers}
        with self._http.stream(
            "POST",
            self._url("/api/research"),
            headers=merged_headers,
            params={"query": str(query or "")},
        ) as resp:
            body_text = ""
            if resp.status_code < 200 or resp.status_code >= 300:
                try:
                    body_text = resp.read().decode("utf-8", errors="ignore")
                except Exception:
                    body_text = ""
                raise WeaverApiError(status=resp.status_code, path="/api/research", body_text=body_text)

            buffer = ""
            for chunk in resp.iter_bytes():
                try:
                    buffer += chunk.decode("utf-8", errors="ignore")
                except Exception:
                    continue

                lines = buffer.split("\n")
                buffer = lines.pop() or ""
                for raw_line in lines:
                    line = raw_line.strip()
                    if not line.startswith("0:"):
                        continue
                    try:
                        parsed = json.loads(line[2:])
                    except Exception:
                        continue
                    if isinstance(parsed, dict) and "type" in parsed and "data" in parsed:
                        yield parsed  # type: ignore[misc]

            tail = buffer.strip()
            if tail.startswith("0:"):
                try:
                    parsed = json.loads(tail[2:])
                except Exception:
                    parsed = None
                if isinstance(parsed, dict) and "type" in parsed and "data" in parsed:
                    yield parsed  # type: ignore[misc]

    def list_sessions(self, *, limit: int | None = None, status: str | None = None) -> Any:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = int(limit)
        if status is not None:
            params["status"] = status
        return self.request_json("/api/sessions", params=params or None)

    def get_session(self, thread_id: str) -> Any:
        safe_id = _encode_path_param(thread_id)
        return self.request_json(f"/api/sessions/{safe_id}")

    def get_evidence(self, thread_id: str) -> Any:
        safe_id = _encode_path_param(thread_id)
        return self.request_json(f"/api/sessions/{safe_id}/evidence")

    def list_export_templates(self) -> Any:
        return self.request_json("/api/export/templates")

    def export_report(
        self,
        thread_id: str,
        *,
        format: str = "pdf",
        template: str = "default",
        title: str = "Research Report",
    ) -> tuple[bytes, str | None]:
        safe_id = _encode_path_param(thread_id)
        resp = self._http.get(
            self._url(f"/api/export/{safe_id}"),
            headers={"Accept": "*/*", **self.headers},
            params={"format": format, "template": template, "title": title},
        )
        body = resp.content or b""
        if resp.status_code < 200 or resp.status_code >= 300:
            raise WeaverApiError(
                status=resp.status_code,
                path=f"/api/export/{safe_id}",
                body_text=body.decode("utf-8", errors="ignore"),
            )
        return body, resp.headers.get("content-type")
