import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { fetchPublicConfig } from '../lib/publicConfig'

test('public config retries failures, shares in-flight requests, and caches a successful response', async (t) => {
  let respond: () => Promise<Response> = async () => { throw new Error('Backend starting') }
  const fetch = t.mock.method(globalThis, 'fetch', () => respond())

  assert.deepEqual(await Promise.all([fetchPublicConfig(), fetchPublicConfig()]), [null, null])
  assert.equal(fetch.mock.callCount(), 1)

  respond = async () => new Response('', { status: 503 })
  assert.equal(await fetchPublicConfig(), null)
  assert.equal(fetch.mock.callCount(), 2)

  respond = async () => new Response('invalid json')
  assert.equal(await fetchPublicConfig(), null)
  assert.equal(fetch.mock.callCount(), 3)

  const config = {
    version: 'test',
    defaults: { port: 8001, primary_model: 'provider/model', reasoning_model: 'provider/model' },
    features: {},
    streaming: {},
    models: { default: 'provider/model', options: ['provider/model'] },
  }
  respond = async () => Response.json(config)
  assert.deepEqual(await fetchPublicConfig(), config)
  assert.deepEqual(await fetchPublicConfig(), config)
  assert.equal(fetch.mock.callCount(), 4)
})
