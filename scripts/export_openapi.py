from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def build_openapi_spec() -> Dict[str, Any]:
    from main import app

    return app.openapi()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Weaver OpenAPI spec as JSON.")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="",
        help="Write JSON to this path (defaults to stdout).",
    )
    args = parser.parse_args(argv)

    spec = build_openapi_spec()
    payload = json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True)

    output_path = (args.output or "").strip()
    if output_path:
        Path(output_path).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
