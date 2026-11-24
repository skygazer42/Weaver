import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { StorageService } from '../lib/storage-service'

test('project chat histories, messages, and resumable runs stay in their workspace', (t) => {
  const localStorage = Object.create({
    getItem(this: Record<string, string>, key: string) { return Object.hasOwn(this, key) ? this[key] : null },
    setItem(this: Record<string, string>, key: string, value: string) { this[key] = value },
    removeItem(this: Record<string, string>, key: string) { delete this[key] },
  })
  Object.defineProperty(globalThis, 'window', { value: { localStorage }, configurable: true })
  t.after(() => Reflect.deleteProperty(globalThis, 'window'))

  const sessionId = 'same-id'
  for (const workspace of [undefined, 'alpha', 'beta']) {
    const name = workspace ?? 'general'
    StorageService.saveHistory([{ id: sessionId, title: name }], workspace)
    StorageService.saveSessionMessages(sessionId, [name], workspace)
    StorageService.setRun(sessionId, { id: name, searchMode: 'agent' }, workspace)
  }

  StorageService.saveRunSnapshot(sessionId, { id: 'alpha', searchMode: 'agent', lastEventId: 1 }, 'alpha')
  assert.equal(StorageService.getRun(sessionId, 'alpha')?.lastEventId, 1)
  assert.equal(StorageService.getRun(sessionId, 'beta')?.lastEventId, undefined)

  StorageService.clearAll('alpha')
  assert.deepEqual(StorageService.getHistory('alpha'), [])
  assert.deepEqual(StorageService.getSessionMessages(sessionId, 'alpha'), [])
  assert.equal(StorageService.getRecentRunSession('alpha'), null)
  assert.equal(StorageService.getRun(sessionId, 'alpha'), null)
  assert.deepEqual(StorageService.getSessionMessages(sessionId), ['general'])
  assert.deepEqual(StorageService.getSessionMessages(sessionId, 'beta'), ['beta'])

  StorageService.clearAll()
  assert.deepEqual(StorageService.getHistory(), [])
  assert.deepEqual(StorageService.getHistory('beta'), [{ id: sessionId, title: 'beta' }])
  assert.equal(StorageService.getRecentRunSession('beta'), sessionId)
  assert.equal(StorageService.getRun(sessionId, 'beta')?.id, 'beta')
})
