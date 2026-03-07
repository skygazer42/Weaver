#!/usr/bin/env python3
"""
Probe Weaver's browser live stream WebSocket endpoint.

This is a lightweight diagnostic tool for reports like:
  - "Live view only shows one frame and looks stuck"
  - "Not sure if backend is still sending frames"

It connects to:
  /api/browser/{thread_id}/stream

Then:
  - sends {"action": "start", "quality": ..., "max_fps": ...}
  - prints receive FPS (all `frame` messages)
  - prints update FPS (non-duplicate frames based on base64 + url/title signature)
  - reports first-frame latency (useful for sandbox cold starts)

Typical usage:
  python scripts/browser_stream_probe.py <thread_id>
  python scripts/browser_stream_probe.py <thread_id> --max-fps 10 --duration 30
  python scripts/browser_stream_probe.py <thread_id> --navigate https://example.com

Auth notes:
  - If WEAVER_INTERNAL_API_KEY is set in the backend, the WS endpoint requires:
      Authorization: Bearer <WEAVER_INTERNAL_API_KEY>
      X-Weaver-User: <principal id>
  - This script will automatically read those values from environment/.env via
    `common.config.settings` when available.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure repo root is on sys.path when running as:
#   python scripts/browser_stream_probe.py ...
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from common.config import settings as _WEAVER_SETTINGS  # type: ignore
except Exception:  # pragma: no cover
    _WEAVER_SETTINGS = None  # type: ignore


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _truncate(text: str, limit: int = 120) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _base_url_default() -> str:
    # Keep consistent with frontend default.
    raw = _env("NEXT_PUBLIC_API_URL", "") or _env("WEAVER_BASE_URL", "")
    if raw:
        return raw.rstrip("/")
    if _WEAVER_SETTINGS is not None:
        try:
            port = int(getattr(_WEAVER_SETTINGS, "port", 8001) or 8001)
        except Exception:
            port = 8001
        return f"http://127.0.0.1:{port}"
    return "http://127.0.0.1:8001"


def _to_ws_base(base_url: str) -> str:
    raw = (base_url or "").strip().rstrip("/")
    if raw.startswith("ws://") or raw.startswith("wss://"):
        return raw
    if raw.startswith("http://"):
        return "ws://" + raw[len("http://") :]
    if raw.startswith("https://"):
        return "wss://" + raw[len("https://") :]
    # Bare host:port
    return "ws://" + raw.lstrip("/")


def _auth_headers(
    *,
    api_key: str,
    user_header: str,
    user: str,
    disable_auth: bool,
) -> Dict[str, str]:
    if disable_auth:
        return {}

    internal_key = (api_key or "").strip()
    if not internal_key and _WEAVER_SETTINGS is not None:
        internal_key = (getattr(_WEAVER_SETTINGS, "internal_api_key", "") or "").strip()
    if not internal_key:
        return {}

    header_name = (user_header or "").strip()
    if not header_name and _WEAVER_SETTINGS is not None:
        header_name = (getattr(_WEAVER_SETTINGS, "auth_user_header", "") or "").strip()
    header_name = header_name or "X-Weaver-User"

    principal = (user or "").strip() or _env("WEAVER_TEST_USER", "probe")
    return {
        "Authorization": f"Bearer {internal_key}",
        header_name: principal,
    }


@dataclass
class ProbeStats:
    start_monotonic: float
    connected_monotonic: float
    first_frame_monotonic: Optional[float] = None

    frames_total: int = 0
    frames_unique_total: int = 0
    frames_dup_total: int = 0

    pings_total: int = 0
    statuses_total: int = 0
    acks_total: int = 0
    errors_total: int = 0
    other_total: int = 0

    frames_window: int = 0
    unique_window: int = 0
    dup_window: int = 0

    last_url: str = ""
    last_title: str = ""

    last_frame_data: Optional[str] = None
    last_frame_meta_sig: str = ""


def _parse_frame_meta(meta: Any) -> Tuple[str, str, str]:
    if not isinstance(meta, dict):
        return "", "", "::"
    url = meta.get("url") or meta.get("page_url") or ""
    title = meta.get("title") or ""
    url_s = url if isinstance(url, str) else ""
    title_s = title if isinstance(title, str) else ""
    sig = f"{url_s}::{title_s}"
    return url_s, title_s, sig


async def _probe_stream(
    *,
    thread_id: str,
    base_url: str,
    quality: int,
    max_fps: int,
    duration_s: float,
    first_frame_timeout_s: float,
    navigate_url: str,
    show_status: bool,
    show_frames: bool,
    disable_auth: bool,
    api_key: str,
    user_header: str,
    user: str,
) -> int:
    ws_base = _to_ws_base(base_url)
    ws_url = ws_base.rstrip("/") + f"/api/browser/{thread_id}/stream"
    headers = _auth_headers(
        api_key=api_key,
        user_header=user_header,
        user=user,
        disable_auth=disable_auth,
    )

    print(f"[probe] ws_url={ws_url}", flush=True)
    if headers:
        # Avoid printing secrets; only show that auth is enabled.
        print("[probe] auth=enabled (internal_api_key)", flush=True)
    else:
        print("[probe] auth=none", flush=True)

    try:
        import websockets
    except Exception as e:  # pragma: no cover
        print(f"[probe] ERROR: missing dependency 'websockets': {e}", file=sys.stderr, flush=True)
        print("[probe] Hint: `pip install websockets` (or install uvicorn[standard])", file=sys.stderr)
        return 2

    start_monotonic = time.monotonic()
    stats = ProbeStats(start_monotonic=start_monotonic, connected_monotonic=start_monotonic)

    async def _report_loop() -> None:
        last_report = time.monotonic()
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            elapsed = now - stats.start_monotonic

            # First-frame latency / waiting hint.
            if stats.first_frame_monotonic is None and elapsed >= 1.0:
                waited = now - stats.connected_monotonic
                print(
                    f"[t+{elapsed:5.1f}s] waiting first frame… ({waited:0.1f}s since connect)",
                    flush=True,
                )

            rx = stats.frames_window
            uniq = stats.unique_window
            dup = stats.dup_window
            stats.frames_window = 0
            stats.unique_window = 0
            stats.dup_window = 0

            if rx or uniq or dup:
                url = _truncate(stats.last_url, 70)
                title = _truncate(stats.last_title, 70)
                extra = ""
                if rx > 0 and uniq == 0:
                    extra = " (static)"
                if url or title:
                    extra += f" url={url!r} title={title!r}"
                print(
                    f"[t+{elapsed:5.1f}s] RX={rx:>2} fps  UI={uniq:>2} upd/s  dup={dup:>2}{extra}",
                    flush=True,
                )

            # Stop after duration.
            if duration_s > 0 and elapsed >= duration_s:
                break

            # Keep output cadence stable-ish.
            drift = (time.monotonic() - last_report) - 1.0
            if drift > 0.5:
                last_report = time.monotonic()

    async def _recv_loop(ws) -> None:
        while True:
            raw = await ws.recv()
            if raw is None:
                break

            try:
                data = json.loads(raw)
            except Exception:
                stats.other_total += 1
                continue

            if not isinstance(data, dict):
                stats.other_total += 1
                continue

            msg_type = data.get("type")
            if msg_type == "frame":
                stats.frames_total += 1
                stats.frames_window += 1

                if stats.first_frame_monotonic is None:
                    stats.first_frame_monotonic = time.monotonic()
                    latency = stats.first_frame_monotonic - stats.connected_monotonic
                    print(f"[probe] first_frame_latency={latency:0.2f}s", flush=True)

                next_data = data.get("data")
                next_data_s = next_data if isinstance(next_data, str) else ""
                url, title, meta_sig = _parse_frame_meta(data.get("metadata"))

                is_dup = bool(
                    next_data_s
                    and next_data_s == stats.last_frame_data
                    and meta_sig == stats.last_frame_meta_sig
                )
                if is_dup:
                    stats.frames_dup_total += 1
                    stats.dup_window += 1
                else:
                    stats.frames_unique_total += 1
                    stats.unique_window += 1
                    stats.last_frame_data = next_data_s
                    stats.last_frame_meta_sig = meta_sig
                    stats.last_url = url
                    stats.last_title = title

                if show_frames:
                    source = data.get("source") if isinstance(data.get("source"), str) else ""
                    stamp = data.get("timestamp")
                    stamp_s = f"{stamp:0.3f}" if isinstance(stamp, (int, float)) else "?"
                    tag = "dup" if is_dup else "new"
                    print(
                        f"[frame] {tag} source={source!r} ts={stamp_s} url={_truncate(url,80)!r}",
                        flush=True,
                    )

            elif msg_type == "status":
                stats.statuses_total += 1
                msg = data.get("message")
                if show_status:
                    print(f"[status] {msg}", flush=True)

            elif msg_type == "ack":
                stats.acks_total += 1
                # Only print failures by default (status spam isn't helpful).
                ok = data.get("ok")
                if ok is False:
                    print(
                        f"[ack] ok=false action={data.get('action')!r} error={data.get('error')!r}",
                        flush=True,
                    )

            elif msg_type == "ping":
                stats.pings_total += 1

            elif msg_type == "error":
                stats.errors_total += 1
                msg = data.get("message")
                print(f"[error] {msg}", file=sys.stderr, flush=True)

            else:
                stats.other_total += 1

    open_timeout = max(10.0, float(first_frame_timeout_s or 0.0))
    close_timeout = 10.0

    connect_kwargs: Dict[str, Any] = {
        "open_timeout": open_timeout,
        "close_timeout": close_timeout,
        # Disable built-in ping; the server already sends keepalive `ping` events.
        "ping_interval": None,
    }
    if headers:
        try:
            params = inspect.signature(websockets.connect).parameters
        except Exception:
            params = {}

        # websockets<14: extra_headers
        # websockets>=14: additional_headers
        if "additional_headers" in params:
            connect_kwargs["additional_headers"] = headers
        elif "extra_headers" in params:
            connect_kwargs["extra_headers"] = headers
        else:
            # Best-effort fallback: prefer the modern name.
            connect_kwargs["additional_headers"] = headers

    try:
        async with websockets.connect(ws_url, **connect_kwargs) as ws:
            stats.connected_monotonic = time.monotonic()

            # Start streaming immediately (frontend behavior).
            await ws.send(
                json.dumps(
                    {
                        "action": "start",
                        "quality": int(quality or 60),
                        "max_fps": int(max_fps or 5),
                    }
                )
            )

            if navigate_url:
                await ws.send(json.dumps({"action": "navigate", "url": str(navigate_url).strip()}))

            reporter = asyncio.create_task(_report_loop(), name="browser-stream-probe-report")
            receiver = asyncio.create_task(_recv_loop(ws), name="browser-stream-probe-recv")

            # Enforce a hard first-frame timeout (useful to detect "cold-start stuck").
            if first_frame_timeout_s and first_frame_timeout_s > 0:
                deadline = stats.connected_monotonic + float(first_frame_timeout_s)
            else:
                deadline = None

            while True:
                await asyncio.sleep(0.25)
                elapsed = time.monotonic() - stats.start_monotonic
                if duration_s > 0 and elapsed >= duration_s:
                    break
                if deadline is not None and stats.first_frame_monotonic is None and time.monotonic() >= deadline:
                    print(
                        f"[probe] ERROR: no frame within {first_frame_timeout_s:0.1f}s (cold start or sandbox stuck)",
                        file=sys.stderr,
                        flush=True,
                    )
                    break
                if receiver.done():
                    break

            # Stop streaming to reduce backend load.
            try:
                await ws.send(json.dumps({"action": "stop"}))
            except Exception:
                pass

            for task in (reporter, receiver):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    except asyncio.CancelledError:  # pragma: no cover
        raise
    except KeyboardInterrupt:  # pragma: no cover
        raise
    except Exception as e:
        print(
            f"[probe] ERROR: ws connect/run failed: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    elapsed_total = max(0.001, time.monotonic() - stats.start_monotonic)
    rx_avg = stats.frames_total / elapsed_total
    uniq_avg = stats.frames_unique_total / elapsed_total

    first_latency = None
    if stats.first_frame_monotonic is not None:
        first_latency = stats.first_frame_monotonic - stats.connected_monotonic

    print(
        "[summary] "
        f"elapsed={elapsed_total:0.1f}s "
        f"frames={stats.frames_total} (avg_rx={rx_avg:0.2f} fps) "
        f"unique={stats.frames_unique_total} (avg_ui={uniq_avg:0.2f} upd/s) "
        f"dup={stats.frames_dup_total} "
        f"status={stats.statuses_total} ack={stats.acks_total} ping={stats.pings_total} error={stats.errors_total} "
        + (
            f"first_frame_latency={first_latency:0.2f}s"
            if first_latency is not None
            else "first_frame_latency=none"
        ),
        flush=True,
    )
    return 0 if stats.errors_total == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Probe /api/browser/{thread_id}/stream WebSocket.")
    p.add_argument("thread_id", help="Weaver thread id (same id used by BrowserViewer).")
    p.add_argument("--base-url", default=_base_url_default(), help="Backend base URL (http(s)://...)")
    p.add_argument("--quality", type=int, default=60, help="JPEG quality (1-100). Default: 60")
    p.add_argument("--max-fps", type=int, default=5, help="Max FPS requested from the server. Default: 5")
    p.add_argument(
        "--duration",
        type=float,
        default=90.0,
        help="How long to run (seconds). Default: 90. Use 0 to run until Ctrl+C.",
    )
    p.add_argument(
        "--first-frame-timeout",
        type=float,
        default=90.0,
        help="Fail if no frame arrives within N seconds (0 disables). Default: 90",
    )
    p.add_argument("--navigate", default="", help="Optional URL to navigate after starting.")
    p.add_argument("--show-status", action="store_true", help="Print status messages.")
    p.add_argument("--show-frames", action="store_true", help="Print a line per frame (verbose).")

    p.add_argument("--no-auth", action="store_true", help="Do not send WEAVER_INTERNAL_API_KEY headers.")
    p.add_argument("--api-key", default="", help="Override WEAVER_INTERNAL_API_KEY (do not print).")
    p.add_argument(
        "--user-header",
        default="",
        help="Override WEAVER_AUTH_USER_HEADER (default reads settings/auth_user_header).",
    )
    p.add_argument("--user", default="", help="Override principal id header value (default WEAVER_TEST_USER).")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    try:
        return asyncio.run(
            _probe_stream(
                thread_id=args.thread_id,
                base_url=args.base_url,
                quality=args.quality,
                max_fps=args.max_fps,
                duration_s=float(args.duration or 0.0),
                first_frame_timeout_s=float(args.first_frame_timeout or 0.0),
                navigate_url=str(args.navigate or "").strip(),
                show_status=bool(args.show_status),
                show_frames=bool(args.show_frames),
                disable_auth=bool(args.no_auth),
                api_key=str(args.api_key or "").strip(),
                user_header=str(args.user_header or "").strip(),
                user=str(args.user or "").strip(),
            )
        )
    except KeyboardInterrupt:  # pragma: no cover
        print("\n[probe] interrupted", flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
