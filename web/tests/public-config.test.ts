import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { fetchPublicConfig, getPublicModels, type PublicConfigResponse } from '../lib/publicConfig'

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
    models: { default: 'provider/model', reasoning_default: 'provider/reasoner', options: ['provider/model', 'provider/reasoner'], source: 'gateway' },
  }
  respond = async () => Response.json(config)
  assert.deepEqual(await fetchPublicConfig(), config)
  assert.deepEqual(await fetchPublicConfig(), config)
  assert.equal(fetch.mock.callCount(), 4)
})

test('public model normalization preserves routing defaults and every catalog source', () => {
  const config: PublicConfigResponse = {
    version: 'test',
    defaults: { port: 8001, primary_model: 'gpt-4.1', reasoning_model: 'o3-mini' },
    features: {}, streaming: {},
  }
  for (const source of ['gateway', 'siliconflow', 'static'] as const) {
    const models = { default: 'deepseek-chat', reasoning_default: 'deepseek-reasoner', options: ['deepseek-chat', 'deepseek-reasoner'], source }
    assert.deepEqual(getPublicModels({ ...config, models }), models)
  }
  assert.deepEqual(getPublicModels(config), {
    default: 'gpt-4.1', reasoning_default: 'o3-mini', options: ['gpt-4.1'], source: 'static',
  })
  assert.equal(getPublicModels({ ...config, models: { default: '', options: ['gpt-4.1'] } })?.reasoning_default, 'o3-mini')
  assert.equal(getPublicModels(null), null)
})
