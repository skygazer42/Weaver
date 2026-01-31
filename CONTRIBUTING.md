# Contributing

Thanks for helping improve Weaver!

## Prerequisites

- Python 3.11+
- Node.js 18+ (Node 20+ recommended)
- pnpm (for `web/`)

## Backend Setup

```bash
make setup
```

Optional heavy tool dependencies (desktop automation / Office docs / crawler extras):

```bash
make setup-full
```

## Frontend Setup

```bash
cd web
pnpm install
```

## Common Commands

```bash
# Lint (ruff)
make lint

# Format (ruff format)
make format

# Tests (pytest)
make test

# Everything (lint + tests + secret scan)
make check
```

## pre-commit

Install hooks:

```bash
.venv/bin/pre-commit install
```

Run on all files:

```bash
.venv/bin/pre-commit run -a
```

## Secret Handling

- Never commit real API keys.
- Use `.env.example` as a template and keep `.env` local.
- Local scan:

```bash
.venv/bin/python scripts/secret_scan.py
```

## CI Expectations

Pull requests should pass:
- Backend lint + tests
- Secret scan
- Frontend lint + build
- Docker image build
