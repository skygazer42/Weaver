import type { components } from '../api-types'

export type EvidencePassageItem = components['schemas']['EvidencePassageItem']

export type EvidenceHeadingGroup = {
  key: string
  headingPath: string[]
  passages: EvidencePassageItem[]
}

export type EvidencePageGroup = {
  url: string
  headings: EvidenceHeadingGroup[]
  totalPassages: number
  uniquePassages: number
}

function normalizeHeadingGroup(passage: EvidencePassageItem): { key: string; headingPath: string[] } {
  const rawPath = Array.isArray(passage.heading_path) ? passage.heading_path : []
  const headingPath = rawPath.map(String).map(s => s.trim()).filter(Boolean)

  const keyFromPath = headingPath.length ? headingPath.join(' / ') : ''
  if (keyFromPath) return { key: keyFromPath, headingPath }

  const heading = String(passage.heading ?? '').trim()
  if (heading) return { key: heading, headingPath: [] }

  return { key: 'Ungrouped', headingPath: [] }
}

function passageDedupeKey(passage: EvidencePassageItem): string {
  const hash = String(passage.snippet_hash ?? '').trim()
  if (hash) return `h:${hash}`
  return `c:${passage.start_char}:${passage.end_char}`
}

export function groupEvidencePassages(passages: EvidencePassageItem[]): EvidencePageGroup[] {
  const pagesByUrl = new Map<
    string,
    {
      url: string
      headingMap: Map<string, EvidenceHeadingGroup>
      totalPassages: number
      uniquePassages: number
      seen: Set<string>
    }
  >()

  for (const passage of passages || []) {
    if (!passage || typeof passage !== 'object') continue
    const url = String(passage.url ?? '').trim()
    if (!url) continue

    let page = pagesByUrl.get(url)
    if (!page) {
      page = {
        url,
        headingMap: new Map(),
        totalPassages: 0,
        uniquePassages: 0,
        seen: new Set(),
      }
      pagesByUrl.set(url, page)
    }

    page.totalPassages += 1

    const key = passageDedupeKey(passage)
    if (page.seen.has(key)) continue
    page.seen.add(key)
    page.uniquePassages += 1

    const heading = normalizeHeadingGroup(passage)
    let group = page.headingMap.get(heading.key)
    if (!group) {
      group = { key: heading.key, headingPath: heading.headingPath, passages: [] }
      page.headingMap.set(heading.key, group)
    }
    group.passages.push(passage)
  }

  return Array.from(pagesByUrl.values()).map(page => ({
    url: page.url,
    headings: Array.from(page.headingMap.values()),
    totalPassages: page.totalPassages,
    uniquePassages: page.uniquePassages,
  }))
}

