#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OPENAPI_JSON=""
if [[ "${1:-}" == "--openapi-json" ]]; then
  OPENAPI_JSON="${2:-}"
  shift 2
fi

if [[ -z "$OPENAPI_JSON" ]]; then
  OPENAPI_JSON="/tmp/weaver-openapi.json"

  PY="$ROOT_DIR/.venv/bin/python"
  if [[ ! -x "$PY" ]]; then
    if command -v python3.11 >/dev/null 2>&1; then
      PY="$(command -v python3.11)"
    elif command -v python3 >/dev/null 2>&1; then
      PY="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
      PY="$(command -v python)"
    else
      echo "No python interpreter found (tried .venv/bin/python, python3.11, python3, python)" >&2
      exit 1
    fi
  fi

  "$PY" "$ROOT_DIR/scripts/export_openapi.py" --output "$OPENAPI_JSON"
fi

if [[ ! -f "$OPENAPI_JSON" ]]; then
  echo "OpenAPI JSON not found: $OPENAPI_JSON" >&2
  exit 1
fi

pnpm -C "$ROOT_DIR/web" exec openapi-typescript "$OPENAPI_JSON" -o "$ROOT_DIR/web/lib/api-types.ts"
pnpm -C "$ROOT_DIR/web" exec openapi-typescript "$OPENAPI_JSON" -o "$ROOT_DIR/sdk/typescript/src/openapi-types.ts"

# Fail if generation changed the committed file.
git -C "$ROOT_DIR" diff --exit-code -- web/lib/api-types.ts sdk/typescript/src/openapi-types.ts
