from __future__ import annotations

import argparse
import py_compile
import sys
from pathlib import Path


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "web",  # frontend (TypeScript); keep python gate backend-only by default
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def _iter_python_files(root: Path, *, exclude_dirs: set[str]) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in exclude_dirs for part in path.parts):
            continue
        paths.append(path)
    return paths


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Fail fast if any tracked Python source fails to compile.")
    parser.add_argument(
        "--root",
        default=".",
        help="Repo root to scan (default: current directory).",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name to exclude (can be repeated).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[compile] root not found: {root}", file=sys.stderr)
        return 2

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    exclude_dirs.update({d.strip() for d in args.exclude_dir if d.strip()})

    paths = _iter_python_files(root, exclude_dirs=exclude_dirs)
    if not paths:
        print("[compile] no python files found", file=sys.stderr)
        return 2

    failed = 0
    for path in paths:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as e:
            failed += 1
            print(f"[compile] FAIL {path}: {e.msg}", file=sys.stderr)

    if failed:
        print(f"[compile] {failed} file(s) failed to compile", file=sys.stderr)
        return 1

    print(f"[compile] OK ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

