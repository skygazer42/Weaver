# Weaver Optimization Round 2 Design (2026-01-31)

**Goal:** Add another small, low-risk batch of “mainstream web research project” hardening: OSS hygiene (license/security), full-stack CI, reproducible dev commands, and a few runtime correctness fixes with tests.

## Context

Weaver is a full-stack AI agent platform (FastAPI + LangGraph backend, Next.js frontend) focused on web research / deep research workflows.

Round 1 already added:
- Basic CI (Python lint + tests) + pre-commit
- Secret scan guardrails
- Optional dependency split
- Safer parsing (no `eval`)
- Test discovery hygiene + additional tests

Round 2 focuses on the next set of common gaps seen in production-ish research agent repos:
- Missing OSS hygiene files (LICENSE / SECURITY / CONTRIBUTING)
- CI that only covers the backend (frontend breaks can ship unnoticed)
- Docker build drift (Dockerfile paths that don’t match build context)
- Missing request correlation header for support/debugging
- Health endpoint reporting “database connected” even when no DB is configured

## Approaches Considered

### Option A: Big refactor / packaging overhaul

Convert to a fully packaged Python project with multi-module versioning, strict typing, and a major restructure.

- Pros: long-term cleanliness
- Cons: high risk; breaks users; hard to validate quickly

### Option B (chosen): Incremental quality gates + targeted correctness fixes

Add the missing project hygiene/maintenance pieces and expand CI to cover the frontend and Docker build, plus a few small behavior fixes guarded by tests.

- Pros: high ROI, low risk; improves reliability immediately; keeps changes reviewable
- Cons: still not a full packaging overhaul (intentionally)

## Design Principles

- **One commit per task**: keep changes easy to review/revert.
- **Evidence before claims**: run lint/tests/builds for each behavior change.
- **No breaking changes without tests**: add regression tests for behavioral fixes.
- **Keep installs fast**: keep heavy tooling optional where reasonable.

## Success Criteria

- Project includes standard OSS governance docs: LICENSE, SECURITY, CONTRIBUTING.
- CI covers: backend lint/tests, secret scan, frontend lint/build, and a Docker build.
- Dev workflow includes `make format` / `make check` and pre-commit formatting.
- Runtime correctness:
  - `X-Request-ID` is returned for each HTTP request.
  - `/health` reports DB status based on actual configuration, not truthiness of an in-memory checkpointer.

