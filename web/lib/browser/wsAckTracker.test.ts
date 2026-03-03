import { describe, expect, it, vi } from 'vitest'

import { WsAckTracker } from './wsAckTracker'

describe('WsAckTracker', () => {
  it('resolves when matching ack arrives', async () => {
    vi.useFakeTimers()
    try {
      const tracker = new WsAckTracker({ timeoutMs: 1000 })

      const promise = tracker.waitFor('a1')
      tracker.resolve({ type: 'ack', id: 'a1', ok: true, action: 'mouse', timestamp: 123 })

      await expect(promise).resolves.toMatchObject({ ok: true, id: 'a1', action: 'mouse' })
    } finally {
      vi.useRealTimers()
    }
  })

  it('rejects with timeout when ack does not arrive', async () => {
    vi.useFakeTimers()
    try {
      const tracker = new WsAckTracker({ timeoutMs: 10 })

      const promise = tracker.waitFor('a2')

      // Attach rejection handler before the timer fires to avoid unhandled rejections.
      const assertion = expect(promise).rejects.toThrow(/timeout/i)
      await vi.advanceTimersByTimeAsync(11)
      await assertion
    } finally {
      vi.useRealTimers()
    }
  })

  it('rejects all pending requests on close', async () => {
    vi.useFakeTimers()
    try {
      const tracker = new WsAckTracker({ timeoutMs: 1000 })

      const p1 = tracker.waitFor('p1')
      const p2 = tracker.waitFor('p2')

      const a1 = expect(p1).rejects.toThrow(/closed/i)
      const a2 = expect(p2).rejects.toThrow(/closed/i)
      tracker.rejectAll(new Error('socket closed'))

      await a1
      await a2
    } finally {
      vi.useRealTimers()
    }
  })
})
