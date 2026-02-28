"""
Comprehensive backend test runner (real + unit tests).

Runs:
1) Unit tests (pytest)
2) Live API integration sweep (real uvicorn + real HTTP/WS)

This is intended for local/dev verification with a filled `.env`.

Usage:
    python scripts/backend_full_test.py
    python scripts/backend_full_test.py --no-ws
    python scripts/backend_full_test.py --timeout 90 --out /tmp/weaver-backend-report.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(cmd: List[str], *, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> int:
    print(f"[full-test] $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env)
    return int(proc.returncode)


def _default_report_path() -> Path:
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return _repo_root() / "logs" / f"backend_full_test_{ts}.json"


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--timeout", type=float, default=60.0, help="Live API request timeout seconds")
    p.add_argument("--no-ws", action="store_true", help="Skip WebSocket checks in live sweep")
    p.add_argument(
        "--out",
        default="",
        help="Write a combined JSON report to this path (default: logs/backend_full_test_*.json)",
    )
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    report_path = Path(args.out) if args.out else _default_report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) Unit tests
    unit_rc = _run([sys.executable, "-m", "pytest", "-q"], cwd=_repo_root())
    if unit_rc != 0:
        payload: Dict[str, Any] = {
            "ok": False,
            "unit_tests": {"ok": False, "exit_code": unit_rc},
            "live_api": {"ok": None, "exit_code": None},
        }
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[full-test] wrote report: {report_path}")
        return unit_rc

    # 2) Live API sweep
    live_report = report_path.with_suffix(".live.json")
    live_cmd = [
        sys.executable,
        "scripts/live_api_smoke.py",
        "--timeout",
        str(float(args.timeout)),
        "--out",
        str(live_report),
    ]
    if not args.no_ws:
        live_cmd.insert(2, "--ws")
    live_rc = _run(live_cmd, cwd=_repo_root(), env=os.environ.copy())

    payload2: Dict[str, Any] = {
        "ok": unit_rc == 0 and live_rc == 0,
        "unit_tests": {"ok": unit_rc == 0, "exit_code": unit_rc},
        "live_api": {"ok": live_rc == 0, "exit_code": live_rc, "report": str(live_report)},
    }
    report_path.write_text(json.dumps(payload2, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[full-test] wrote report: {report_path}")
    return live_rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

