#!/usr/bin/env bash

# One-command “real” verification:
# - backend unit tests
# - OpenAPI TS drift guard
# - real-HTTP live API smoke (spawns uvicorn)
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

