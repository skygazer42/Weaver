# Browser acceptance tests

With the frontend dependencies installed and the project Python environment active, run the following from the repository root.

```sh
python -m pip install playwright==1.65.2
python -m playwright install chromium
pnpm -C web build
pnpm -C web e2e
```

Build with the default `NEXT_PUBLIC_API_URL`. The suite starts the production build and a deterministic HTTP fixture on loopback. Every test uses a fresh Chromium context. It exercises Agent history, approval and refusal, reload and stop, large tool output downloads, and Deep Research evidence in the browser. The fixture records submitted run IDs and cursors. Provider and backend execution are covered by the separate Python suites.

Set `WEAVER_E2E_BROWSER_CHANNEL=chrome` to use an installed Google Chrome. Pass a `unittest` test name after `e2e` to run one scenario. Failed scenarios write a Playwright trace under `web/test-results/`, alongside the Next.js log.
