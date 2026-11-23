export interface LegacyChatStreamEvent {
  type: string
  data: any
}

export interface LegacyChatStreamState {
  buffer: string
}

interface ConsumeLegacyChatStreamOptions {
  flush?: boolean
}

export function createLegacyChatStreamState(): LegacyChatStreamState {
  return { buffer: '' }
}

export function consumeLegacyChatStreamChunk(
  state: LegacyChatStreamState,
  chunk: string,
  options: ConsumeLegacyChatStreamOptions = {},
): LegacyChatStreamEvent[] {
  state.buffer += chunk

  const lines = state.buffer.split('\n')
  state.buffer = options.flush ? '' : lines.pop() ?? ''

  const events: LegacyChatStreamEvent[] = []

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line || !line.startsWith('0:')) continue

    try {
      const event = JSON.parse(line.slice(2)) as LegacyChatStreamEvent
      if (event?.type) {
        events.push(event)
      }
    } catch (error) {
      if (!options.flush) {
        state.buffer = `${rawLine}\n${state.buffer}`
        break
      }

      console.error('Error parsing flushed stream line:', error)
    }
  }

  return events
}

export function consumeSseChatStreamChunk(
  state: LegacyChatStreamState,
  chunk: string,
  options: ConsumeLegacyChatStreamOptions = {},
): LegacyChatStreamEvent[] {
  state.buffer += chunk
  const frames = state.buffer.split(/\r?\n\r?\n/)
  state.buffer = options.flush ? '' : frames.pop() ?? ''
  const events: LegacyChatStreamEvent[] = []
  for (const frame of frames) {
    const lines = frame.split(/\r?\n/)
    const type = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
    const data = lines.filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, '')).join('\n')
    if (!data) continue
    const payload = JSON.parse(data)
    if (payload?.type) events.push(payload)
    else if (type) events.push({ type, data: payload })
  }
  return events
}
