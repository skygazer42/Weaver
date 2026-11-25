import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { formatCommandArgs, parseCommandArgs, parseMcpServersJson, recordToRows, rowsToRecord } from '../lib/mcp'
import { translations } from '../lib/i18n/translations'

test('imports standard Claude Desktop / Cursor and flat MCP configurations', () => {
  const server = { command: 'npx', args: ['-y', 'mcp-server'], env: { TOKEN: ' secret ' }, cwd: 'C:/work' }
  const expected = { local: { ...server, type: 'stdio', enabled: true } }
  assert.deepEqual(parseMcpServersJson(JSON.stringify({ mcpServers: { local: server } })), expected)
  assert.deepEqual(parseMcpServersJson(JSON.stringify({ local: server })), expected)
  assert.deepEqual(parseMcpServersJson('{"mcpServers":{}}'), {})
})

test('infers HTTP, SSE and stdio and normalizes transport aliases', () => {
  const servers = parseMcpServersJson(JSON.stringify({
    http: { url: 'https://example.com/mcp', headers: { Authorization: 'Bearer token' } },
    sse: { url: 'https://example.com/SSE/?token=x' },
    local: { command: ' python ', enabled: false },
    alias: { type: 'http', url: 'https://example.com/mcp' },
    hyphen: { transport: 'streamable-http', url: 'https://example.com/mcp' },
  }))
  assert.deepEqual(Object.values(servers).map(server => server.type), ['streamable_http', 'sse', 'stdio', 'streamable_http', 'streamable_http'])
  assert.equal(servers.local.command, 'python')
  assert.equal(servers.local.enabled, false)
  assert.deepEqual(servers.http.headers, { Authorization: 'Bearer token' })
})

test('rejects invalid JSON, server shapes and invalid transport fields', () => {
  for (const raw of ['', '{', 'null', '[]', '{"mcpServers":[]}', '{"server":null}', '{"server":{}}',
    '{"server":{"type":"ftp","url":"https://example.com"}}', '{"server":{"type":"constructor","url":"https://example.com"}}', '{"server":{"url":"javascript:alert(1)"}}',
    '{"server":{"command":"npx","args":"-y"}}', '{"server":{"command":"npx","env":{"TOKEN":null}}}',
    '{" server ":{"command":"npx"},"server":{"command":"node"}}']) {
    assert.throws(() => parseMcpServersJson(raw), raw)
  }
})

test('headers and env rows round trip without changing secret values', () => {
  const values = { Authorization: 'Bearer secret ', EMPTY: '', PATH: 'C:\\Program Files\\bin' }
  assert.deepEqual(rowsToRecord(recordToRows(values)), values)
  assert.deepEqual(rowsToRecord([{ key: ' TOKEN ', value: ' secret ' }, { key: '', value: '' }]), { TOKEN: ' secret ' })
  assert.deepEqual(recordToRows(), [])
  assert.throws(() => rowsToRecord([{ key: '', value: 'secret' }]))
  assert.throws(() => rowsToRecord([{ key: 'TOKEN', value: 'a' }, { key: ' TOKEN ', value: 'b' }]))
  assert.equal(Object.getPrototypeOf(rowsToRecord([{ key: '__proto__', value: 'value' }])), Object.prototype)
})

test('command args keep spaces, quotes, backslashes and empty values', () => {
  const args = ['-y', 'C:\\Program Files\\server', 'a "quote"', '']
  assert.deepEqual(parseCommandArgs(formatCommandArgs(args)), args)
  assert.deepEqual(parseCommandArgs(''), [])
  assert.throws(() => parseCommandArgs('npx -y'))
  assert.throws(() => parseCommandArgs('[1]'))
})

test('all four locales translate the MCP manager and composer', () => {
  const keys = Object.keys(translations.en).filter(key => key.startsWith('mcp'))
  for (const locale of ['en', 'zh', 'ja', 'ko'] as const) {
    for (const key of keys) assert.ok((translations[locale] as Record<string, string>)[key], `${locale}: ${key}`)
  }
})
