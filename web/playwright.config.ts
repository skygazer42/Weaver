import { defineConfig, devices } from '@playwright/test'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

function readDotenvValue(envPath: string, key: string): string | null {
  try {
    const raw = fs.readFileSync(envPath, 'utf-8')
    for (const line of raw.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      const eq = trimmed.indexOf('=')
      if (eq <= 0) continue
      const k = trimmed.slice(0, eq).trim()
      if (k !== key) continue
      let v = trimmed.slice(eq + 1).trim()
      if (
        (v.startsWith('"') && v.endsWith('"')) ||
        (v.startsWith("'") && v.endsWith("'"))
      ) {
        v = v.slice(1, -1)
      }
      return v.trim() || null
    }
    return null
  } catch {
    return null
  }
}

const repoRoot = path.resolve(__dirname, '..')
const dotenvPort = readDotenvValue(path.join(repoRoot, '.env'), 'PORT')

function stripProxyEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const cleaned: NodeJS.ProcessEnv = { ...env }
  for (const key of [
    'HTTP_PROXY',
    'HTTPS_PROXY',
    'ALL_PROXY',
    'NO_PROXY',
    'http_proxy',
    'https_proxy',
    'all_proxy',
    'no_proxy',
  ]) {
    delete cleaned[key]
  }
  return cleaned
}

const backendPort = (
  process.env.E2E_BACKEND_PORT ||
  dotenvPort ||
  process.env.PORT ||
  '8001'
).trim()

const backendBaseUrl = `http://127.0.0.1:${backendPort}`
const webBaseUrl = process.env.E2E_WEB_BASE_URL?.trim() || 'http://localhost:3100'

const webHost = (() => {
  try {
    return new URL(webBaseUrl).hostname || 'localhost'
  } catch {
    return 'localhost'
  }
})()

const webPort = (() => {
  try {
    const parsed = new URL(webBaseUrl)
    if (parsed.port) return Number(parsed.port)
  } catch {
    // ignore
  }
  return 3100
})()

const reuseExistingServer = ['1', 'true', 'yes', 'y', 'on'].includes(
  (process.env.E2E_REUSE_EXISTING_SERVER || '').trim().toLowerCase()
)

// Keep backend side-effects (data/, collaboration store, etc.) out of the repo.
// This makes `pnpm -C web e2e` reproducible and keeps `git status` clean.
const e2eDataDir =
  process.env.E2E_DATA_DIR?.trim() ||
  fs.mkdtempSync(path.join(os.tmpdir(), 'weaver-e2e-data-'))

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 3 * 60 * 1000,
  expect: { timeout: 30_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: webBaseUrl,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    acceptDownloads: true,
  },
  webServer: [
    {
      cwd: repoRoot,
      command: `python -m uvicorn main:app --host 127.0.0.1 --port ${backendPort}`,
      url: `${backendBaseUrl}/health`,
      timeout: 180_000,
      reuseExistingServer,
      env: {
        ...stripProxyEnv(process.env),
        PORT: backendPort,
        WEAVER_DATA_DIR: e2eDataDir,
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      cwd: __dirname,
      command: `pnpm exec next dev --webpack -H ${webHost} -p ${webPort}`,
      url: webBaseUrl,
      timeout: 180_000,
      reuseExistingServer,
      env: {
        ...stripProxyEnv(process.env),
        NEXT_PUBLIC_API_URL: backendBaseUrl,
        NEXT_DIST_DIR: '.next-e2e',
      },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
