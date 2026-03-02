#!/usr/bin/env bash

# One-command “real” verification:
# - backend unit tests
# - OpenAPI TS drift guard
# - real-HTTP live API smoke (spawns uvicorn)
#   - includes /api/health/agent + tools/search diagnostics probes
# - Playwright full-stack e2e (headless + headed via Xvfb)
#
# Notes:
# - We unset common proxy env vars to avoid flaky behavior in httpx/E2B/Playwright.
# - We set WEAVER_DATA_DIR so runtime artifacts don't dirty the git checkout.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

unset http_proxy https_proxy all_proxy \
  HTTP_PROXY HTTPS_PROXY ALL_PROXY \
  no_proxy NO_PROXY || true

PY="${REPO_ROOT}/.venv/bin/python"
if [ ! -x "${PY}" ]; then
  PY="python"
fi

export WEAVER_DATA_DIR="${WEAVER_DATA_DIR:-/tmp/weaver-data-verify}"
mkdir -p "${WEAVER_DATA_DIR}"

free_port() {
  "${PY}" - <<'PY'
import socket

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
print(port)
PY
}

# Playwright e2e starts real backend + frontend dev servers. Pick free ports by
# default so local services don't cause false failures.
export E2E_BACKEND_PORT="${E2E_BACKEND_PORT:-$(free_port)}"
export E2E_WEB_BASE_URL="${E2E_WEB_BASE_URL:-http://127.0.0.1:$(free_port)}"

run() {
  echo "+ $*"
  "$@"
}

run "${PY}" -m pytest -q
run bash scripts/check_openapi_ts_types.sh
run "${PY}" scripts/live_api_smoke.py --ws --timeout 30

run pnpm -C web e2e

if command -v xvfb-run >/dev/null 2>&1; then
  run xvfb-run -a pnpm -C web e2e:headed
else
  echo "xvfb-run not found; skipping headed e2e"
fi
