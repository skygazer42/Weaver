#!/usr/bin/env python3
"""Simple secret scanner for the git working tree.

This is NOT a replacement for dedicated secret scanners.
It exists to catch the most common accidental leaks (API keys in committed files).

Usage:
  python scripts/secret_scan.py

Exit codes:
  0 - no suspicious tokens found
  1 - suspicious tokens found
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Known placeholder/sample tokens intentionally present in the repo.
ALLOWLIST = {
    # Placeholder E2B key used to detect "example" configs.
    "e2b_39ce8c3d299470afd09b42629c436edec32728d8",
}


# Keep patterns intentionally broad, but avoid false positives.
PATTERNS: dict[str, re.Pattern[str]] = {
    "openai_like": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "tavily": re.compile(r"tvly-[A-Za-z0-9_-]{10,}"),
    "e2b": re.compile(r"e2b_[A-Za-z0-9]{10,}"),
    "mem0": re.compile(r"m0-[A-Za-z0-9]{10,}"),
}


BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".tgz",
    ".mp4",
    ".mov",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line_no: int
    kind: str
    token: str


def _mask(token: str) -> str:
    if len(token) <= 10:
        return token
    return f"{token[:6]}...{token[-4:]}"


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], text=True)
    return [p for p in out.splitlines() if p.strip()]


def _scan_file(path: str) -> list[Finding]:
    p = Path(path)
    if p.suffix.lower() in BINARY_EXTS:
        return []

    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pat in PATTERNS.items():
            for m in pat.finditer(line):
                token = m.group(0)
                if token in ALLOWLIST:
                    continue
                findings.append(Finding(path=path, line_no=line_no, kind=kind, token=token))
    return findings


def main() -> int:
    findings: list[Finding] = []
    for f in _tracked_files():
        findings.extend(_scan_file(f))

    if not findings:
        print("secret-scan: OK (no suspicious tokens found)")
        return 0

    print("secret-scan: FAILED (suspicious tokens found)")
    for item in findings:
        print(f"- {item.path}:{item.line_no} [{item.kind}] {_mask(item.token)}")

    print("\nIf these are real secrets, rotate them and remove from git history if needed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
