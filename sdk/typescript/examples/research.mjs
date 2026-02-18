import { WeaverClient } from '../dist/index.js'

const baseUrl = process.env.WEAVER_BASE_URL || 'http://127.0.0.1:8001'
const client = new WeaverClient({ baseUrl })

const payload = {
  messages: [{ role: 'user', content: 'Give me a 3-bullet summary of Weaver.' }],
  stream: true,
}

for await (const ev of client.chatSse(payload)) {
  if (ev.type === 'text') process.stdout.write(String(ev.data?.content || ''))
  if (ev.type === 'done') break
}

process.stdout.write('\n')
console.log('thread_id:', client.lastThreadId)

