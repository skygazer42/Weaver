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

## Project workflows

Open `/workspace` to create a project, add instructions and decisions, and upload source files. **Chat in project** uses these sources and recent deliverables. **Requirements spec** drafts requirements with evidence and acceptance criteria. **Release brief** reads a public GitHub release and the README at its tag. Each completed task has a Markdown download and can be revised from task history.

Generating and saving project deliverables requires `DATABASE_URL` and a configured model provider. Project files and metadata use the existing workspace storage.

In **New task**, choose **Every 24 hours** or **Every 7 days** under **Repeat**, then set the first run in your local time. Each occurrence reads the current project instructions and sources. Under **Scheduled tasks** you can see the next run, open the latest result, pause, resume, or delete the plan. Run history and downloads stay available after deletion.

The API service runs schedules in the background. On startup, an overdue active plan queues one run and advances to its next interval. A resumed plan starts at its next future interval. The intervals are fixed durations, so the displayed local hour can change when clocks shift.

The project browser test drives the production Web build against the Python API and PostgreSQL. It uses test doubles for the model and GitHub responses. From the repo root, set `WEAVER_PROJECT_BROWSER_E2E=1` and `WEAVER_TEST_POSTGRES_DSN` to a test database whose user can create and drop schemas. Then run `python -m pytest -q tests/test_project_browser.py`. A failed run saves `web/test-results/project-runtime.zip`.
