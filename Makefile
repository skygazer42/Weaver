PYTHON ?= python3.11
VENV_DIR ?= .venv
VENV_BIN := $(VENV_DIR)/bin
PIP := $(VENV_BIN)/pip
PY := $(VENV_BIN)/python

.PHONY: help setup setup-full test lint

help:
	@echo "Targets:"
	@echo "  setup       - Create venv and install core + dev dependencies"
	@echo "  setup-full  - Install optional tool dependencies (if requirements-optional.txt exists)"
	@echo "  test        - Run pytest"
	@echo "  lint        - Run ruff"

setup:
	@test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	@$(PIP) install -U pip
	@$(PIP) install -r requirements.txt -r requirements-dev.txt

setup-full: setup
	@test -f requirements-optional.txt && $(PIP) install -r requirements-optional.txt || true

test:
	@$(PY) -m pytest -q

lint:
	@$(VENV_BIN)/ruff check .
