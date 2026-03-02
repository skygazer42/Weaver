from __future__ import annotations

from pathlib import Path


_DEFAULT_RELOAD_SUBDIRS: tuple[str, ...] = (
    # Backend code
    "agent",
    "common",
    "tools",
    "triggers",
    # Runtime prompts + SDK types often change during dev
    "prompts",
    "sdk",
)

# Uvicorn reload uses watchfiles, which can exceed OS watch limits when large
# frontend dependency trees are included (e.g. `web/node_modules`).
_DEFAULT_RELOAD_EXCLUDES: tuple[str, ...] = (
    "web",
    "web/node_modules",
    "web/.next",
    ".git",
    ".venv",
    "__pycache__",
    "logs",
    "data",
    "screenshots",
)


def get_uvicorn_reload_dirs(repo_root: Path | str | None = None) -> list[str]:
    """
    Return reload dirs for uvicorn that avoid common watch-limit crashes.

    We include the repo root (to pick up `main.py`) and a curated set of backend
    subdirectories, while excluding the heavy frontend trees separately.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parent.parent
    dirs: list[Path] = [root]

    for name in _DEFAULT_RELOAD_SUBDIRS:
        candidate = root / name
        if candidate.is_dir():
            dirs.append(candidate)

    # De-dupe while keeping order.
    seen: set[str] = set()
    out: list[str] = []
    for p in dirs:
        val = str(p)
        if val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def get_uvicorn_reload_excludes() -> list[str]:
    """Return exclude globs for uvicorn reload."""
    return list(_DEFAULT_RELOAD_EXCLUDES)

