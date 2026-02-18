import type { SseEvent, StreamEvent } from './types.js'

export function parseSseFrame(frame: string): SseEvent | null {
  const text = String(frame ?? '')
  if (!text.trim()) return null

  const lines = text.split('\n').map((l) => l.trimEnd())
  let eventName = ''
  let idText = ''
  const dataLines: string[] = []

  for (const line of lines) {
    if (!line) continue
    if (line.startsWith(':')) continue

    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim()
      continue
    }

    if (line.startsWith('id:')) {
      idText = line.slice('id:'.length).trim()
      continue
    }

    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
      continue
    }
  }

  if (dataLines.length === 0) return null
  const dataText = dataLines.join('\n')

  let parsed: unknown
  try {
    parsed = JSON.parse(dataText) as unknown
  } catch {
    return null
  }

  const out: SseEvent = { data: parsed }
  if (eventName) out.event = eventName
  if (idText) {
    const idNum = Number(idText)
    if (Number.isFinite(idNum)) out.id = idNum
  }

  return out
}

export async function* readSseEvents(response: Response): AsyncGenerator<SseEvent> {
  if (!response.body) return

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    buffer = buffer.replace(/\r\n/g, '\n')

    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const frame of frames) {
      const parsed = parseSseFrame(frame)
      if (parsed) yield parsed
    }
  }

  const tail = buffer.trim()
  if (tail) {
    const parsed = parseSseFrame(tail)
    if (parsed) yield parsed
  }
}

export async function* readDataStreamEvents(response: Response): AsyncGenerator<StreamEvent> {
  if (!response.body) return

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const rawLine of lines) {
      const line = rawLine.trim()
      if (!line) continue
      if (!line.startsWith('0:')) continue

      try {
        const parsed = JSON.parse(line.slice(2)) as unknown
        if (parsed && typeof parsed === 'object' && 'type' in parsed && 'data' in parsed) {
          yield parsed as StreamEvent
        }
      } catch {
        continue
      }
    }
  }

  const tail = buffer.trim()
  if (tail.startsWith('0:')) {
    try {
      const parsed = JSON.parse(tail.slice(2)) as unknown
      if (parsed && typeof parsed === 'object' && 'type' in parsed && 'data' in parsed) {
        yield parsed as StreamEvent
      }
    } catch {
      // ignore
    }
  }
}
