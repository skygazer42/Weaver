# Weaver Optimization Round 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Continue hardening Weaver like a mainstream “web research / agent” project: OSS hygiene, full-stack CI, Docker correctness, better dev workflows, and a few small runtime fixes guarded by tests.

**Architecture:** No redesign. Prefer small, reviewable changes with 1 commit per task.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph/LangChain, pytest, ruff, Next.js, pnpm, GitHub Actions, Docker.

---

## Baseline Setup (pre-task)

- Create a worktree branch (do not work on `main`):
  - `git worktree add ~/.config/superpowers/worktrees/Weaver/optimize-2026-01-31-2 -b chore/optimize-2026-01-31-2`
- Install backend deps:
  - `make setup`
- Verify baseline:
  - `make lint && make test`

---

### Task 1: Add Round 2 Design Doc

**Files:**
- Create: `docs/plans/2026-01-31-weaver-optimization-round2-design.md`

**Steps:**
1. Write the design doc.
2. Verify: `git diff --check`.
3. Commit: `git commit -m "docs: add round2 optimization design"`.

---

### Task 2: Add This Round 2 Implementation Plan

**Files:**
- Create: `docs/plans/2026-01-31-weaver-optimization-round2-plan.md`

**Steps:**
1. Write the plan.
2. Verify: `git diff --check`.
3. Commit: `git commit -m "docs: add round2 optimization plan"`.

---

### Task 3: Add MIT LICENSE

**Files:**
- Create: `LICENSE`

**Steps:**
1. Add standard MIT license text.
2. Verify: `git diff --check`.
3. Commit: `git commit -m "docs: add MIT license"`.

---

### Task 4: Add CONTRIBUTING Guide

**Files:**
- Create: `CONTRIBUTING.md`

**Steps:**
1. Document setup (`make setup`, `make test`, `make lint`, `pre-commit install`).
2. Mention optional deps (`make setup-full`) and secret scan.
3. Verify: `git diff --check`.
4. Commit: `git commit -m "docs: add contributing guide"`.

---

### Task 5: Add SECURITY Policy

**Files:**
- Create: `SECURITY.md`

**Steps:**
1. Add reporting instructions + reminders about secret scan and `.env`.
2. Verify: `git diff --check`.
3. Commit: `git commit -m "docs: add security policy"`.

---

### Task 6: Add Dependabot Config

**Files:**
- Create: `.github/dependabot.yml`

**Steps:**
1. Enable updates for:
   - GitHub Actions
   - pip (`/`)
   - npm/pnpm (`/web`)
2. Verify: `git diff --check`.
3. Commit: `git commit -m "ci: add dependabot config"`.

---

### Task 7: Add Frontend CI Job

**Files:**
- Modify: `.github/workflows/ci.yml`

**Steps:**
1. Add a `frontend` job that installs pnpm deps and runs `pnpm -C web lint` + `pnpm -C web build`.
2. Verify backend still passes: `make lint && make test`.
3. Commit: `git commit -m "ci: add frontend lint/build job"`.

---

### Task 8: Add `pip check` to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Steps:**
1. Add a step after install: `python -m pip check`.
2. Verify locally: `make test`.
3. Commit: `git commit -m "ci: run pip check"`.

---

### Task 9: Add `compileall` to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Steps:**
1. Add: `python -m compileall -q .`.
2. Verify locally: `make test`.
3. Commit: `git commit -m "ci: compileall"`.

---

### Task 10: Add Make Targets (`format`, `check`)

**Files:**
- Modify: `Makefile`

**Steps:**
1. Add `make format` (ruff format) and `make check` (lint + test + secret scan).
2. Verify: `make check`.
3. Commit: `git commit -m "chore: add format/check make targets"`.

---

### Task 11: Add Ruff Format Hook to pre-commit

**Files:**
- Modify: `.pre-commit-config.yaml`

**Steps:**
1. Add `ruff-format` hook.
2. Verify: `.venv/bin/pre-commit run -a`.
3. Commit: `git commit -m "chore: add ruff format to pre-commit"`.

---

### Task 12: Run Ruff Format Across Repo

**Files:**
- Modify: (various python files)

**Steps:**
1. Run: `.venv/bin/ruff format .`.
2. Verify: `make lint && make test`.
3. Commit: `git commit -m "style: ruff format"`.

---

### Task 13: Add `X-Request-ID` Response Header

**Files:**
- Modify: `main.py`
- Create: `tests/test_request_id_header.py`

**Steps:**
1. RED: test `/health` response includes header `X-Request-ID`.
2. Run targeted test (expect FAIL).
3. GREEN: set the header in request logging middleware.
4. Run: `make test`.
5. Commit: `git commit -m "obs: add x-request-id header"`.

---

### Task 14: Fix `/health` DB Status Reporting

**Files:**
- Modify: `main.py`
- Create: `tests/test_health_db_status.py`

**Steps:**
1. RED: test `/health` returns `database: not configured` when `DATABASE_URL` is unset.
2. Run targeted test (expect FAIL).
3. GREEN: base DB status on `settings.database_url`.
4. Run: `make test`.
5. Commit: `git commit -m "fix: report db status correctly in health"`.

---

### Task 15: Add Tests for Fallback Search Engine Selection

**Files:**
- Create: `tests/test_fallback_search.py`

**Steps:**
1. Add tests covering:
   - alias mapping (e.g., `google` -> `google_cse`)
   - skipping unknown engines
   - returning the first engine that yields results
2. Verify: `make test`.
3. Commit: `git commit -m "tests: cover fallback search engine selection"`.

---

### Task 16: Add Tests for Provider Error Redaction Helpers

**Files:**
- Create: `tests/test_search_provider_redaction.py`

**Steps:**
1. Add tests for `_sanitize_error_message` and `_is_valid_api_key` in `tools/search/providers.py`.
2. Fix patterns if tests reveal gaps.
3. Verify: `make test`.
4. Commit: `git commit -m "tests: cover search provider redaction"`.

---

### Task 17: Fix Dockerfile COPY Paths

**Files:**
- Modify: `docker/Dockerfile`

**Steps:**
1. Fix `COPY` sources to be relative to build context root.
2. Verify locally: `docker build -f docker/Dockerfile .`.
3. Commit: `git commit -m "docker: fix Dockerfile copy paths"`.

---

### Task 18: Add Docker Build to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Steps:**
1. Add a job/step to run: `docker build -f docker/Dockerfile .`.
2. Verify locally: `make test`.
3. Commit: `git commit -m "ci: build docker image"`.

---

### Task 19: Rebrand Backend Strings (Manus -> Weaver)

**Files:**
- Modify: `main.py`
- Modify: `scripts/dev.sh`
- Modify: `scripts/setup.sh`

**Steps:**
1. Rename obvious user-facing strings (API title / service names / script banners).
2. Verify: `make test`.
3. Commit: `git commit -m "chore: rebrand backend strings to Weaver"`.

---

### Task 20: Rebrand Frontend UI Strings (Manus -> Weaver)

**Files:**
- Modify: `web/components/layout/Sidebar.tsx`
- Modify: `web/components/chat/ChatInterface.tsx`
- (Optional) Modify: `web/package.json` name

**Steps:**
1. Replace UI labels.
2. Verify locally:
   - `pnpm -C web install`
   - `pnpm -C web lint`
   - `pnpm -C web build`
3. Commit: `git commit -m "chore: rebrand frontend strings to Weaver"`.
