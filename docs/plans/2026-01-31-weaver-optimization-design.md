# Weaver Optimization Design (2026-01-31)

**Goal:** Improve Weaver's security, developer experience, and reliability (especially around “web research” workflows) via small, low-risk, test-verified changes.

## Context

Weaver is a full-stack AI agent platform (FastAPI + LangGraph backend, Next.js frontend) with “web research / deep research” workflows plus a large tool ecosystem (browser automation, sandbox execution, MCP, etc.).

The repo currently has a few “production readiness” gaps that are typical in fast-moving web-research projects:

- Secrets appear to be committed in `.env` / `.env.example`
- Dependency installation is heavy and can trigger slow resolver backtracking
- Some files carry UTF-8 BOMs; a couple of pytest warnings indicate upcoming breakages
- Missing standardized quality gates (lint/format/CI/pre-commit) for steady iteration

## Approaches Considered

### Option A: Minimal “quick patch” hardening

Focus only on removing secrets and fixing a couple warnings.

- Pros: fastest, lowest risk
- Cons: doesn’t improve iteration speed or prevent regressions

### Option B (chosen): Incremental hardening + DX improvements

Keep architecture intact; prioritize safety, reproducibility, and small refactors with tests.

- Pros: high ROI; sets up sustainable workflow (CI, linting, pre-commit); improves web-research robustness without rewrites
- Cons: moderate number of commits/changes

### Option C: Major restructure (packaging, module split, dependency redesign)

Move to `pyproject.toml` packaging, large refactors, big dependency/feature reshapes.

- Pros: clean long-term structure
- Cons: high risk; likely to break things; hard to validate in 1 pass

## Design Principles

- **Small commits, always verified**: each task ends in a commit with tests/lint evidence.
- **Secure-by-default**: no secrets tracked; lightweight secret scanning guardrails.
- **Optional tool deps**: keep core install and CI fast; heavy tools become optional extras where possible.
- **Web-research safety**: remove unsafe parsing patterns (e.g., `eval`) and improve robustness with unit tests.
- **No sweeping refactors**: avoid “big bang” changes; prioritize maintainability and confidence.

## Success Criteria

- No committed secrets in tracked files (`.env` removed from git; examples sanitized)
- `pytest` runs cleanly (no deprecated hooks; no “return non-None” warnings)
- Lint/format standard added (ruff) + CI + pre-commit hooks
- Dependency workflow documented and faster to install (especially avoiding resolver backtracking)
- Changes remain backwards-compatible for the existing API surface; tests stay green
