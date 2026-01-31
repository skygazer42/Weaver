# Security Policy

## Reporting a Vulnerability

If you discover a security issue, please do **not** open a public GitHub issue.

Instead, report it privately:
- Email the maintainer, or
- Use GitHub Security Advisories (if enabled for this repository)

Please include:
- A clear description of the issue
- Steps to reproduce
- Impact assessment (what an attacker can do)
- Suggested fix (if you have one)

## Secrets

- Do not commit real API keys.
- Keep `.env` local; use `.env.example` as a template.
- This repo includes a lightweight secret scan for common key patterns:

```bash
.venv/bin/python scripts/secret_scan.py
```

If you accidentally committed a real secret:
1. Rotate the key immediately.
2. Remove it from the codebase.
3. Consider rewriting git history if it was pushed.

## Dependency Updates

This project uses CI and automated checks to reduce common security footguns.
When updating dependencies, ensure tests and CI remain green.
