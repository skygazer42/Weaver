import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { createWorkspaceRunTransport, mergeWorkspaceRuns, type WorkspaceRun } from '../lib/workspace'

const queued: WorkspaceRun = {
  id: 'run-1',
  file_id: 'file-1',
  model: 'example/model',
  prompt: 'Compare regions',
  status: 'queued',
  step: 'queued',
  error: null,
  created_at: '2026-11-22T12:00:00Z',
  updated_at: '2026-11-22T12:00:00Z',
}

test('posts the workspace run fields and reads the API progress event', async (t) => {
  const url = 'https://weaver.example/api/workspaces/workspace-1/runs'
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response([
    `data: ${JSON.stringify({ type: 'data-run', id: queued.id, data: queued })}\n\n`,
    'data: {"type":"finish"}\n\n',
    'data: [DONE]\n\n',
  ].join(''), { headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' } }))

  const payload = { file_id: 'file-1', model: 'example/model', prompt: 'Compare regions' }
  const stream = await createWorkspaceRunTransport(url).sendMessages({
    trigger: 'submit-message',
    chatId: 'workspace-1',
    messageId: undefined,
    messages: [],
    abortSignal: undefined,
    body: payload,
  })
  const [requestedUrl, request] = fetch.mock.calls[0].arguments
  assert.equal(requestedUrl, url)
  assert.equal(request?.method, 'POST')
  assert.deepEqual(JSON.parse(String(request?.body)), payload)
  const reader = stream.getReader()
  assert.deepEqual((await reader.read()).value, {
    type: 'data-run',
    id: queued.id,
    data: queued,
  })
  assert.equal((await reader.read()).value?.type, 'finish')
  assert.equal((await reader.read()).done, true)
})

test('a late saved snapshot cannot undo live progress or remove a new run', () => {
  const completed = { ...queued, status: 'completed', step: 'completed', updated_at: '2026-11-22T12:00:30Z' } as const
  const newRun = { ...queued, id: 'run-2', created_at: '2026-11-22T12:01:00Z' }

  assert.deepEqual(mergeWorkspaceRuns([completed, newRun], [queued]), [newRun, completed])
})

test('a saved run can return to the queue after a server restart', () => {
  const writing = { ...queued, status: 'running', step: 'report' } as const
  const restarted = { ...queued, updated_at: '2026-11-22T12:00:30Z' }

  assert.deepEqual(mergeWorkspaceRuns([writing], [restarted]), [restarted])
})
