PYTHON ?= python3.11
VENV_DIR ?= .venv
VENV_BIN := $(VENV_DIR)/bin
PY := $(VENV_BIN)/python

.PHONY: help setup setup-full test lint format secret-scan check web-install web-lint web-build

help:
	@echo "Targets:"
	@echo "  setup       - Create venv and install core + dev dependencies"
	@echo "  setup-full  - Install optional tool dependencies (if requirements-optional.txt exists)"
	@echo "  test        - Run pytest"
	@echo "  lint        - Run ruff"
	@echo "  format      - Run ruff formatter"
	@echo "  secret-scan - Scan tracked files for common API key patterns"
	@echo "  check       - Run lint + tests + secret scan"
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

test:
	@$(PY) -m pytest -q

lint:
	@$(PY) -m ruff check .

format:
	@$(PY) -m ruff format .

secret-scan:
	@$(PY) scripts/secret_scan.py

check: lint test secret-scan

web-install:
	@pnpm -C web install --frozen-lockfile

web-lint:
	@pnpm -C web lint

web-build:
	@pnpm -C web build
