PYTHON ?= python3.11
VENV_DIR ?= .venv
VENV_BIN := $(VENV_DIR)/bin
PY := $(VENV_BIN)/python

.PHONY: help setup setup-full dev dev-reload verify test lint lint-all format secret-scan check openapi-types bench-smoke web-install web-lint web-build

help:
	@echo "Targets:"
	@echo "  setup       - Create venv and install core + dev dependencies"
	@echo "  setup-full  - Install optional tool dependencies (if requirements-optional.txt exists)"
	@echo "  dev         - Start backend (no hot reload)"
	@echo "  dev-reload  - Start backend with opt-in hot reload"
	@echo "  verify      - Run real full-stack verification (headless)"
	@echo "  test        - Run pytest"
	@echo "  lint        - Run ruff (changed files)"
	@echo "  lint-all    - Run ruff (full repo)"
	@echo "  format      - Run ruff formatter"
	@echo "  secret-scan - Scan tracked files for common API key patterns"
	@echo "  check       - Run lint + tests + secret scan"
	@echo "  openapi-types - Regenerate OpenAPI TS types and ensure no drift"
	@echo "  bench-smoke - Run deep research benchmark policy smoke (no execution)"
	@echo "  web-install - Install frontend dependencies (pnpm)"
	@echo "  web-lint    - Run frontend lint (Next.js)"
	@echo "  web-build   - Run frontend build (Next.js)"

setup:
	@test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	@$(PY) -m ensurepip --upgrade >/dev/null 2>&1 || true
	@$(PY) -m pip install -U pip
	@$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

setup-full: setup
	@test -f requirements-optional.txt && $(PY) -m pip install -r requirements-optional.txt || true

dev:
	@$(PY) main.py

dev-reload:
	@DEBUG=true WEAVER_RELOAD=1 $(PY) main.py

verify:
	@$(PY) -m pytest -q
	@bash scripts/check_openapi_ts_types.sh
	@$(PY) scripts/live_api_smoke.py --ws --timeout 30
	@pnpm -C web e2e

test:
	@$(PY) -m pytest -q

lint:
	@bash scripts/ruff_changed_files.sh

lint-all:
	@$(PY) -m ruff check .

format:
	@$(PY) -m ruff format .

secret-scan:
	@$(PY) scripts/secret_scan.py

check: lint test secret-scan

openapi-types:
	@bash scripts/check_openapi_ts_types.sh

bench-smoke:
	@$(PY) scripts/benchmark_deep_research.py --max-cases 3 --mode auto --output /tmp/benchmark_smoke.json

web-install:
	@pnpm -C web install --frozen-lockfile

web-lint:
	@pnpm -C web lint

web-build:
	@pnpm -C web build
