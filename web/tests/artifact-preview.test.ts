import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { buildArtifactSrcDoc, detectArtifactLanguage, getArtifactPreviewKind } from '../lib/artifactPreview'
import { ArtifactsPanel } from '../components/chat/ArtifactsPanel'
import { I18nProvider } from '../lib/i18n/i18n-context'
import { translations } from '../lib/i18n/translations'
import type { Artifact } from '../types/chat'

const artifact = (content: string, fields: Partial<Artifact> = {}): Artifact => ({
  id: 'preview', type: 'report', title: 'Analysis', content, createdAt: 1, updatedAt: 1, ...fields,
})

test('detects HTML documents, interactive snippets, and explicit HTML metadata', () => {
  for (const content of [
    '<!DOCTYPE html><html><body>Report</body></html>',
    '  <html lang="en"><head></head><body>Report</body></html>  ',
    '<style>canvas { width: 100% }</style><canvas id="chart"></canvas><script>drawChart()</script>',
    '<main><h1>Revenue</h1><section><button>Compare</button></section></main>',
    '<!-- report --><div id="chart"></div><script>render()</script>',
  ]) assert.equal(getArtifactPreviewKind(artifact(content)), 'html', content)

  assert.equal(getArtifactPreviewKind(artifact('report', { title: 'REPORT.HTM' })), 'html')
  assert.equal(getArtifactPreviewKind(artifact('report', { mimeType: 'text/html; charset=utf-8' })), 'html')
})

test('detects standalone SVG documents and SVG metadata', () => {
  assert.equal(getArtifactPreviewKind(artifact(' \n<svg viewBox="0 0 100 100"><rect width="100" height="100" /></svg> ')), 'svg')
  assert.equal(getArtifactPreviewKind(artifact('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>')), 'svg')
  assert.equal(getArtifactPreviewKind(artifact('image', { mimeType: 'image/svg+xml' })), 'svg')
  assert.equal(getArtifactPreviewKind(artifact('image', { title: 'Chart.SVG' })), 'svg')
})

test('does not preview source code, Markdown mentions, JSON, or execution logs', () => {
  for (const entry of [
    artifact('import pandas as pd\nhtml = "<html><body>chart</body></html>"', { type: 'code', title: 'report.py' }),
    artifact('"""<html><body>example</body></html>"""', { type: 'code' }),
    artifact('export const Chart = () => <div><canvas /></div>', { type: 'code', title: 'chart.tsx' }),
    artifact('<main>JSX source</main>', { type: 'code', mimeType: 'text/typescript' }),
    artifact('Use <script> or <canvas> for interactive charts.'),
    artifact('# Research\n\nThe `<html>` tag begins a document.\n\n<div>Example</div>'),
    artifact('```html\n<main>example</main>\n```'),
    artifact('<svg></svg> is the chart markup.'),
    artifact('{"html":"<main>Example</main>"}'),
    artifact('[INFO] Rendered <canvas> chart\nDone', { type: 'tool_output' }),
    artifact('<main>logged markup</main>', { type: 'tool_output' }),
    artifact(''),
  ]) assert.equal(getArtifactPreviewKind(entry), null, entry.content)
})

test('infers highlighting from filenames and MIME types', () => {
  for (const [title, expected] of Object.entries({
    'report.html': 'html', 'chart.svg': 'xml', 'report.py': 'python', 'chart.tsx': 'typescript',
    'app.jsx': 'javascript', 'data.json': 'json', 'styles.css': 'css', 'run.sh': 'bash',
    'query.sql': 'sql', 'notes.md': 'markdown',
  })) assert.equal(detectArtifactLanguage(artifact('', { title })), expected)

  for (const [mimeType, expected] of Object.entries({
    'text/html': 'html', 'image/svg+xml': 'xml', 'application/xml': 'xml',
    'text/x-python': 'python', 'application/typescript': 'typescript',
    'text/javascript': 'javascript', 'application/ld+json': 'json', 'text/css': 'css',
    'application/x-sh': 'bash', 'application/sql': 'sql', 'text/markdown': 'markdown',
  })) assert.equal(detectArtifactLanguage(artifact('', { mimeType })), expected)
})

test('infers common code languages from content without treating source strings as HTML', () => {
  for (const [content, expected] of [
    ['<main>Report</main>', 'html'], ['<svg viewBox="0 0 10 10"></svg>', 'xml'],
    ['import pandas as pd\ndef summarize():\n  return 1', 'python'],
    ['interface Point { x: number }', 'typescript'],
    ['const chart = document.querySelector("canvas");', 'javascript'],
    ['{"values": [1, 2, 3]}', 'json'], ['body { color: red; }', 'css'],
    ['#!/bin/bash\necho done', 'bash'], ['SELECT * FROM reports;', 'sql'],
    ['# Research\n\nResults', 'markdown'], ['[INFO] Completed successfully', 'text'],
  ]) assert.equal(detectArtifactLanguage(artifact(content, { type: 'code' })), expected, content)
})

test('builds HTML documents with charset, viewport and network restrictions before artifact scripts', () => {
  const script = '<script>document.body.dataset.ready = "true"</script>'
  for (const content of [
    script + '<main>Chart</main>',
    '<!doctype html><html lang="ja"><head><title>Report</title></head><body>' + script + '</body></html>',
    '<html><body>' + script + '</body></html>',
  ]) {
    const doc = buildArtifactSrcDoc(artifact(content), 'html')
    assert.match(doc, /^<!doctype html>/i)
    assert.match(doc, /<meta charset="utf-8">/)
    assert.match(doc, /name="viewport" content="width=device-width, initial-scale=1"/)
    assert.match(doc, /default-src 'none'/)
    assert.match(doc, /script-src 'unsafe-inline'/)
    assert.match(doc, /connect-src 'none'/)
    assert.match(doc, /base-uri 'none'/)
    assert.ok(doc.indexOf('Content-Security-Policy') < doc.indexOf(script))
    assert.ok(doc.includes(script))
    assert.equal((doc.match(/<html\b/gi) ?? []).length, 1)
  }
})

test('preserves document language and styles while replacing charset and viewport metadata', () => {
  const doc = buildArtifactSrcDoc(artifact('<!doctype html><html lang="ko"><head><meta charset="shift-jis"><meta name="viewport" content="width=200"><style>body { color: red }</style></head><body>보고서</body></html>'), 'html')
  assert.match(doc, /<html lang="ko">/)
  assert.match(doc, /<style>body \{ color: red \}<\/style>/)
  assert.equal((doc.match(/<meta charset=/g) ?? []).length, 1)
  assert.equal((doc.match(/name="viewport"/g) ?? []).length, 1)
  assert.ok(!doc.includes('shift-jis'))
})

test('wraps SVG in a responsive canvas with scripts disabled', () => {
  const svg = '<svg viewBox="0 0 240 120"><text x="10" y="30">Revenue</text></svg>'
  const doc = buildArtifactSrcDoc(artifact(svg), 'svg')
  assert.ok(doc.includes(svg))
  assert.match(doc, /script-src 'none'/)
  assert.match(doc, /width:100%/)
  assert.match(doc, /height:auto/)
  assert.match(doc, /padding:24px/)
  assert.doesNotMatch(doc, /<script\b/i)
})

test('renders isolated previews with strict sandbox permissions and referrer policy', () => {
  const markup = renderToStaticMarkup(createElement(I18nProvider, null, createElement(ArtifactsPanel, {
    artifacts: [artifact('<main>Report</main>', { id: 'html', title: 'report.html' }), artifact('<svg></svg>', { id: 'svg', title: 'chart.svg' })],
  })))
  const frames = [...markup.matchAll(/<iframe\b[^>]*>/g)].map(match => match[0])
  assert.equal(frames.length, 2)
  assert.match(frames[0], /sandbox="allow-scripts"/)
  assert.match(frames[1], /sandbox=""/)
  for (const frame of frames) {
    assert.match(frame, /referrerPolicy="no-referrer"/i)
    assert.doesNotMatch(frame, /allow-same-origin|allow-top-navigation/)
  }
  assert.equal((markup.match(/aria-pressed="true"/g) ?? []).length, 2)
})

test('all four locales translate every artifact viewer control and output label', () => {
  const keys = [
    'artifactsTitle', 'artifactsViewer', 'artifactsDescription', 'artifactView', 'artifactPreview', 'artifactCode',
    'artifactCopy', 'artifactCopied', 'artifactCopyFailed', 'reloadArtifactPreview', 'expandArtifactOutput',
    'collapseArtifactOutput', 'sandboxedArtifactPreview', 'expandArtifacts', 'collapseArtifacts',
    'artifactsFullscreen', 'closeArtifactsViewer', 'artifactLine', 'artifactLines', 'download',
  ] as const
  for (const locale of ['en', 'zh', 'ja', 'ko'] as const) {
    for (const key of keys) assert.ok(translations[locale][key], `${locale}.${key}`)
  }
})
