import { test, expect } from '@playwright/test'

async function sendMessage(page: any, content: string) {
  const input = page.locator('#chat-input')
  const send = page.getByRole('button', { name: 'Send message' })

  await expect(input).toBeVisible({ timeout: 60_000 })
  await expect(input).toBeEditable({ timeout: 60_000 })

  // Next dev + Tailwind can trigger a couple of fast refreshes on first load.
  // Ensure the controlled textarea value sticks before clicking send.
  for (let attempt = 0; attempt < 3; attempt++) {
    await input.fill(content)
    await expect(input).toHaveValue(content, { timeout: 10_000 })
    if (await send.isEnabled().catch(() => false)) return await send.click()
    await page.waitForTimeout(500)
  }

  await expect(send).toBeEnabled({ timeout: 60_000 })
  await send.click()
}

async function waitForStreamToFinish(page: any, timeoutMs: number) {
  const stop = page.getByRole('button', { name: 'Stop generation' })
  await expect(stop).toBeVisible({ timeout: 30_000 })
  await expect(stop).toBeHidden({ timeout: timeoutMs })
}

test('full-stack: chat + research + browser live + comments + export + share', async ({ page }) => {
  // 1) Open app
  await page.goto('/')
  await expect(page.locator('#chat-input')).toBeVisible({ timeout: 60_000 })

  // 2) Chat SSE (ensures basic streaming + thread header propagation)
  const chatPrompt = 'Respond with the single word: pong'
  const chatResPromise = page.waitForResponse((r) => {
    return (
      r.request().method() === 'POST' &&
      r.url().includes('/api/chat/sse') &&
      r.status() < 500
    )
  })
  await sendMessage(page, chatPrompt)
  const chatRes = await chatResPromise
  if (!chatRes.ok()) {
    const body = await chatRes.text().catch(() => '')
    throw new Error(`chat_sse failed: status=${chatRes.status()} body=${body.slice(0, 400)}`)
  }

  // Wait until the UI has a thread id (header actions are only shown once threadId exists).
  await expect(page.getByRole('button', { name: 'Share session' })).toBeVisible({ timeout: 60_000 })
  await waitForStreamToFinish(page, 180_000)

  // 3) Research SSE (produces exportable report)
  const researchPrompt = '/research Write a short (<= 120 words) report about the number 7.'
  const researchResPromise = page.waitForResponse((r) => {
    return r.request().method() === 'POST' && r.url().includes('/api/research/sse')
  })
  await sendMessage(page, researchPrompt)
  const researchRes = await researchResPromise
  if (!researchRes.ok()) {
    const body = await researchRes.text().catch(() => '')
    throw new Error(`research_sse failed: status=${researchRes.status()} body=${body.slice(0, 400)}`)
  }
  await expect(page.getByRole('button', { name: 'Share session' })).toBeVisible({ timeout: 60_000 })
  await waitForStreamToFinish(page, 240_000)

  // 4) Browser live stream (WebSocket + screencast frames)
  // Browser viewer is enabled by default; wait for LIVE indicator and at least one frame.
  await expect(page.getByText('LIVE', { exact: true })).toBeVisible({ timeout: 180_000 })
  await expect(page.getByAltText('Live browser view')).toBeVisible({ timeout: 180_000 })
  // Ensure frames keep arriving (hook reports frames-per-second once per second).
  await expect(page.getByText(/\b[1-9]\d* FPS\b/)).toBeVisible({ timeout: 60_000 })

  // 5) Comments (POST/GET real backend)
  await page.getByRole('button', { name: 'Open comments' }).click()
  await expect(page.getByRole('heading', { name: 'Comments' })).toBeVisible()
  await page.getByPlaceholder('Write a comment...').fill('e2e comment')
  await page.getByPlaceholder('Write a comment...').press('Enter')
  await expect(page.getByText('e2e comment')).toBeVisible({ timeout: 30_000 })
  await page.getByLabel('Close comments').click()

  // 6) Export (HTML is the default; PDF requires optional deps)
  await page.getByRole('button', { name: 'Export report' }).click()
  await expect(page.getByText('Export Report')).toBeVisible()

  const downloadPromise = page.waitForEvent('download', { timeout: 90_000 })
  await page.getByRole('button', { name: 'Export as HTML', exact: true }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename().toLowerCase().endsWith('.html')).toBeTruthy()

  // 7) Share link + share view route
  await page.getByRole('button', { name: 'Share session' }).click()
  await expect(page.getByText('Share Research')).toBeVisible()

  const shareResPromise = page.waitForResponse((r) => {
    return (
      r.request().method() === 'POST' &&
      r.url().includes('/api/sessions/') &&
      r.url().endsWith('/share')
    )
  })
  await page.getByRole('button', { name: 'Create Share Link' }).click()
  const shareRes = await shareResPromise
  if (!shareRes.ok()) {
    const body = await shareRes.text().catch(() => '')
    throw new Error(`share_create failed: status=${shareRes.status()} body=${body.slice(0, 400)}`)
  }
  const shareJson = await shareRes.json().catch(() => null)
  const shareId = shareJson?.share?.id ? String(shareJson.share.id) : ''
  expect(shareId).not.toEqual('')

  await page.goto(`/share/${shareId}`)
  await expect(page.getByText('Shared Session')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('Messages')).toBeVisible()
})
