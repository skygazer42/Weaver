import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { buildStandaloneHtmlReport, buildInteractiveSlidesHtml } from '../lib/reportExport'
import { buildArtifactSrcDoc } from '../lib/artifactPreview'

test('exports Markdown tables and code without interpreting raw HTML', () => {
  const html = buildStandaloneHtmlReport('R&D <2026>', '| A | B |\n| - | - |\n| 1 | 2 |\n\n```js\nconst a = 1\n```\n\n<script>alert(1)</script>')
  assert.match(html, /^<!doctype html>/)
  assert.match(html, /R&amp;D &lt;2026&gt;/)
  assert.match(html, /<table>/)
  assert.match(html, /<pre><code/)
  assert.match(html, /@media print/)
  assert.doesNotMatch(html, /<script>/)
})

test('exports standalone slides with keyboard and button navigation in the existing sandbox', () => {
  const content = buildInteractiveSlidesHtml('Quarterly outlook', '# Quarterly outlook\n\nOverview\n\n## Supply\n\n- More capacity\n\n```md\n## Not a slide\n```\n\n## Demand\n\nMore customers')
  const html = buildArtifactSrcDoc({ type: 'report', title: 'Quarterly outlook', content }, 'html')
  assert.equal((html.match(/<section class="slide"/g) ?? []).length, 3)
  assert.match(html, /1 \/ 3/)
  assert.match(html, /ArrowLeft/)
  assert.match(html, /ArrowRight/)
  assert.match(html, /id="previous"/)
  assert.match(html, /id="next"/)
  assert.match(html, /connect-src 'none'/)
  assert.doesNotMatch(html, /<script[^>]+src=|<link[^>]+href=|onclick=/)
})

test('keeps a quoted heading inside its slide', () => {
  const html = buildInteractiveSlidesHtml('Report', 'Intro\n\n> ## Quoted heading\n> Quoted detail\n\n## Recommendations\n\nNext steps')
  assert.equal((html.match(/<section class="slide"/g) ?? []).length, 2)
  assert.match(html, /<blockquote>\s*<h2>Quoted heading<\/h2>/)
})
