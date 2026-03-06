import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import {
  createLegacyChatStreamState,
  consumeLegacyChatStreamChunk,
} from '../lib/chatStreamProtocol'

test('buffers partial legacy chat stream lines across chunks', () => {
  const state = createLegacyChatStreamState()

  const first = consumeLegacyChatStreamChunk(
    state,
    '0:{"type":"text","data":{"content":"Par',
  )
  const second = consumeLegacyChatStreamChunk(
    state,
    'is"}}\n0:{"type":"done","data":{}}\n',
  )

  assert.deepEqual(first, [])
  assert.deepEqual(second.map((event) => event.type), ['text', 'done'])
  assert.equal(second[0]?.data?.content, 'Paris')
})

test('ignores blank legacy chat stream lines', () => {
  const state = createLegacyChatStreamState()
  const events = consumeLegacyChatStreamChunk(
    state,
    '\n0:{"type":"status","data":{"text":"working"}}\n\n',
  )

  assert.deepEqual(events.map((event) => event.type), ['status'])
  assert.equal(events[0]?.data?.text, 'working')
})
