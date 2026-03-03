export interface WsAckMessage {
  type: 'ack'
  id?: string
  ok: boolean
  action: string
  timestamp: number
  error?: string
  metadata?: Record<string, any>
}

export interface WsAckTrackerOptions {
  timeoutMs?: number
}

type PendingAckEntry = {
  resolve: (ack: WsAckMessage) => void
  reject: (error: Error) => void
  timeoutId: ReturnType<typeof setTimeout>
}

export class WsAckTracker {
  private readonly pending = new Map<string, PendingAckEntry>()
  private readonly timeoutMs: number

  constructor(options: WsAckTrackerOptions = {}) {
    const maybeTimeoutMs = options.timeoutMs
    this.timeoutMs = typeof maybeTimeoutMs === 'number' && maybeTimeoutMs > 0 ? maybeTimeoutMs : 2500
  }

  waitFor(id: string): Promise<WsAckMessage> {
    const key = (id || '').trim()
    if (!key) return Promise.reject(new Error('Missing ack id'))
    if (this.pending.has(key)) return Promise.reject(new Error(`Duplicate ack id: ${key}`))

    return new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        this.pending.delete(key)
        reject(new Error(`Ack timeout: ${key}`))
      }, this.timeoutMs)

      this.pending.set(key, { resolve, reject, timeoutId })
    })
  }

  resolve(ack: WsAckMessage) {
    const key = typeof ack?.id === 'string' ? ack.id.trim() : ''
    if (!key) return

    const entry = this.pending.get(key)
    if (!entry) return

    clearTimeout(entry.timeoutId)
    this.pending.delete(key)
    entry.resolve(ack)
  }

  rejectAll(error: Error) {
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timeoutId)
      entry.reject(error)
    }
    this.pending.clear()
  }

  get pendingCount(): number {
    return this.pending.size
  }
}

