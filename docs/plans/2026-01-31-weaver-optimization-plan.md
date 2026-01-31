# Weaver Optimization Implementation Plan (20 Tasks)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden Weaver for day-to-day development and “web research” workloads: secure configs, predictable installs, clean tests, and quality gates (lint/CI/pre-commit).

**Architecture:** No major redesign. Keep current FastAPI + LangGraph structure; prefer incremental refactors with tests and minimal behavioral change.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph/LangChain, pytest, (add) ruff, GitHub Actions.

---

## Baseline Setup (pre-task)

- Create a worktree branch (do not work on `main`):
  - Run: `git worktree add ~/.config/superpowers/worktrees/Weaver/optimize-2026-01-31 -b chore/optimize-2026-01-31`
- Create venv and install deps:
  - Run: `python3.11 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt`
- Verify baseline tests:
  - Run: `.venv/bin/python -m pytest -q`
  - Expected: green.

---

### Task 1: Add Optimization Design Doc

**Files:**
- Create: `docs/plans/2026-01-31-weaver-optimization-design.md`

**Steps:**
1. Write the design doc (goals, constraints, success criteria).
2. Verify: `git diff --check`.
3. Commit: `git commit -m "docs: add weaver optimization design"`.

---

### Task 2: Add This 20-Task Implementation Plan

**Files:**
- Create: `docs/plans/2026-01-31-weaver-optimization-plan.md`

**Steps:**
1. Write the plan doc (this file).
2. Verify: `git diff --check`.
3. Commit: `git commit -m "docs: add optimization implementation plan"`.

---

### Task 3: Remove Tracked Secrets and Sanitize Env Examples

**Files:**
- Modify: `.env.example`
- Modify: `.gitignore` (only if needed)
- Remove from git index (keep local file): `.env`

**Steps:**
1. Remove `.env` from git tracking (keep local): `git rm --cached .env`.
2. Replace real keys in `.env.example` with placeholders; remove any BOM.
3. Verify: `.venv/bin/python -m pytest -q`.
4. Commit: `git commit -m "security: stop tracking .env; sanitize .env.example"`.

---

### Task 4: Make API Keys Optional in Dev/Test (Settings)

**Files:**
- Modify: `common/config.py`
- Create: `tests/test_settings_defaults.py`

**Steps:**
1. RED: write failing test that `Settings(_env_file=None)` works with missing `OPENAI_API_KEY`.
2. Run: `.venv/bin/python -m pytest -q tests/test_settings_defaults.py` (expect FAIL).
3. GREEN: set safe defaults (e.g., `openai_api_key: str = ""`) and keep behavior for real usage.
4. Run: `.venv/bin/python -m pytest -q` (expect PASS).
5. Commit: `git commit -m "config: allow missing api keys in dev/test"`.

---

### Task 5: Fix PyAutoGUI Availability Detection

**Files:**
- Modify: `tools/automation/computer_use_tool.py`
- Create: `tests/test_computer_use_optional_dep.py`

**Steps:**
1. RED: add test that `build_computer_use_tools()` returns `[]` when pyautogui is unavailable (mock `importlib.util.find_spec`).
2. Run targeted test (expect FAIL).
3. GREEN: implement reliable availability detection without importing pyautogui at module import.
4. Run: `.venv/bin/python -m pytest -q`.
5. Commit: `git commit -m "tools: gate computer_use tools on pyautogui availability"`.

---

### Task 6: Remove UTF-8 BOM From Source Files

**Files:**
- Modify: (strip BOM) `main.py`, `common/cancellation.py`, `common/concurrency.py`, `agent/core/state.py`, `agent/workflows/*`, `prompts/*`, `tools/io/asr.py`, etc.

**Steps:**
1. Strip BOM bytes from affected files only (no other content changes).
2. Verify: `.venv/bin/python -m pytest -q`.
3. Commit: `git commit -m "chore: remove utf-8 boms from source files"`.

---

### Task 7: Fix Pytest Hook Deprecation Warning

**Files:**
- Modify: `tests/conftest.py`

**Steps:**
1. Update `pytest_collect_file` signature to use `file_path: pathlib.Path`.
2. Verify: `.venv/bin/python -m pytest -q` (no deprecation warning).
3. Commit: `git commit -m "tests: update pytest_collect_file hook signature"`.

---

### Task 8: Stop Pytest Collecting Deep Search Routing Script

**Files:**
- Move/Rename: `scripts/test_deep_search_routing.py` -> `scripts/deep_search_routing_check.py`

**Steps:**
1. Rename file + function so it is not collected by pytest.
2. Ensure `python scripts/deep_search_routing_check.py` still works.
3. Verify: `.venv/bin/python -m pytest -q` (no return-not-none warning).
4. Commit: `git commit -m "chore: keep diagnostic scripts out of pytest collection"`.

---

### Task 9: Add Pytest Configuration (Test Discovery)

**Files:**
- Create: `pytest.ini`

**Steps:**
1. Configure pytest to only discover under `tests/`.
2. Verify: `.venv/bin/python -m pytest -q`.
3. Commit: `git commit -m "tests: configure pytest test discovery"`.

---

### Task 10: Remove Unsafe eval() In DeepSearch Parsing

**Files:**
- Modify: `agent/workflows/deepsearch_optimized.py`
- Create: `tests/test_deepsearch_parse_list_output.py`

**Steps:**
1. RED: add test proving list comprehensions are not executed/parsed (expect failure under eval).
2. Run targeted test (expect FAIL).
3. GREEN: replace `eval` with `ast.literal_eval` and keep fallbacks.
4. Run: `.venv/bin/python -m pytest -q`.
5. Commit: `git commit -m "security: replace eval with literal_eval in deepsearch parsing"`.

---

### Task 11: Add Ruff (Lint/Format) Baseline

**Files:**
- Create: `pyproject.toml` (ruff + tooling config)
- Create: `requirements-dev.txt`

**Steps:**
1. Add ruff to dev deps and minimal configuration.
2. Verify: `.venv/bin/pip install -r requirements-dev.txt` then `.venv/bin/ruff --version`.
3. Commit: `git commit -m "chore: add ruff config and dev requirements"`.

---

### Task 12: Fix Ruff Findings (Safe Subset)

**Files:**
- Modify: various (only safe/low-risk fixes)

**Steps:**
1. Run: `.venv/bin/ruff check . --fix`.
2. Verify: `.venv/bin/ruff check .` and `.venv/bin/python -m pytest -q`.
3. Commit: `git commit -m "style: apply ruff fixes"`.

---

### Task 13: Add GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

**Steps:**
1. Add CI running on push/PR: setup python 3.11, install deps, run ruff + pytest.
2. Verify locally: `.venv/bin/python -m pytest -q`.
3. Commit: `git commit -m "ci: add python test and lint workflow"`.

---

### Task 14: Add pre-commit Hooks

**Files:**
- Create: `.pre-commit-config.yaml`

**Steps:**
1. Add hooks: ruff, ruff-format, end-of-file-fixer, trailing-whitespace.
2. Verify: `.venv/bin/pip install pre-commit && .venv/bin/pre-commit run -a`.
3. Commit: `git commit -m "chore: add pre-commit hooks"`.

---

### Task 15: Add Makefile / Dev Commands

**Files:**
- Create: `Makefile` (or `scripts/dev.sh`)

**Steps:**
1. Provide `make setup`, `make test`, `make lint` using `.venv`.
2. Verify: `make test`.
3. Commit: `git commit -m "chore: add make targets for common dev tasks"`.

---

### Task 16: Reduce Dependency Resolver Backtracking (Optional Deps)

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-optional.txt`

**Steps:**
1. Move heavy optional deps (e.g., `browser-use`, `crawl4ai`, `pyautogui`) to optional file.
2. Verify: `.venv/bin/python -m pytest -q`.
3. Commit: `git commit -m "deps: split optional heavy dependencies"`.

---

### Task 17: Add Secret Scan Guardrail

**Files:**
- Create: `scripts/secret_scan.py`
- Modify: `.github/workflows/ci.yml`

**Steps:**
1. Implement a simple regex-based scan for obvious keys.
2. Add CI step to run the scan.
3. Verify: `.venv/bin/python scripts/secret_scan.py`.
4. Commit: `git commit -m "security: add secret scan script and CI step"`.

---

### Task 18: Improve Request Logging Middleware

**Files:**
- Modify: `main.py`

**Steps:**
1. Keep metrics conditional but always log start/end.
2. Verify: `.venv/bin/python -m pytest -q`.
3. Commit: `git commit -m "obs: improve request logging middleware"`.

---

### Task 19: Add Edge-Case Tests for Settings Parsing Helpers

**Files:**
- Create: `tests/test_settings_parsing.py`
- Modify: `common/config.py` (if needed)

**Steps:**
1. Add tests for list parsing helpers with whitespace/empty values.
2. Fix parsing if needed.
3. Verify: `.venv/bin/python -m pytest -q`.
4. Commit: `git commit -m "tests: cover settings parsing edge cases"`.

---

### Task 20: Update README / Docs for New Workflows

**Files:**
- Modify: `README.md`
- Modify: `docs/README.en.md` (as needed)

**Steps:**
1. Update setup instructions: env handling, venv + make targets, optional deps, CI/pre-commit.
2. Verify: `git diff --check`.
3. Commit: `git commit -m "docs: update setup and contribution workflows"`.
