import type { Artifact } from '@/types/chat'

type PreviewArtifact = Pick<Artifact, 'type' | 'title' | 'content' | 'mimeType'>
type PreviewKind = 'html' | 'svg'
type ArtifactLanguage = 'html' | 'xml' | 'python' | 'typescript' | 'javascript' | 'json' | 'css' | 'bash' | 'sql' | 'markdown' | 'text'

const extensionLanguages: Record<string, ArtifactLanguage> = {
  html: 'html', htm: 'html', svg: 'xml', xml: 'xml', py: 'python', ipynb: 'json',
  ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript', mjs: 'javascript', cjs: 'javascript',
  json: 'json', css: 'css', sh: 'bash', bash: 'bash', sql: 'sql', md: 'markdown', markdown: 'markdown',
}

function metadataLanguage(artifact: PreviewArtifact): ArtifactLanguage | undefined {
  const extension = /\.([a-z0-9]+)$/i.exec(artifact.title.trim())?.[1].toLowerCase()
  if (extension && extensionLanguages[extension]) return extensionLanguages[extension]
  const mime = artifact.mimeType?.toLowerCase() ?? ''
  if (/html/.test(mime)) return 'html'
  if (/svg|xml/.test(mime)) return 'xml'
  if (/python/.test(mime)) return 'python'
  if (/typescript/.test(mime)) return 'typescript'
  if (/javascript|ecmascript/.test(mime)) return 'javascript'
  if (/json/.test(mime)) return 'json'
  if (/css/.test(mime)) return 'css'
  if (/shellscript|x-sh\b|bash/.test(mime)) return 'bash'
  if (/sql/.test(mime)) return 'sql'
  if (/markdown/.test(mime)) return 'markdown'
}

export function getArtifactPreviewKind(artifact: PreviewArtifact): PreviewKind | null {
  const mime = artifact.mimeType?.toLowerCase() ?? ''
  const content = artifact.content.trim().replace(/^<\?xml[^>]*>\s*/i, '').replace(/^(?:<!--[\s\S]*?-->\s*)+/, '')
  if (mime.includes('svg') || /\.svg$/i.test(artifact.title.trim())) return 'svg'
  if (mime.includes('html') || /\.html?$/i.test(artifact.title.trim())) return 'html'
  if (artifact.type === 'tool_output') return null
  // Source-file metadata wins over markup embedded in Python strings or JSX.
  const language = metadataLanguage(artifact)
  if (language && language !== 'html' && language !== 'xml') return null
  if (/^<svg\b[\s\S]*<\/svg>\s*$/i.test(content)) return 'svg'
  if (/^(?:<!doctype\s+html(?:\s|>)|<html(?:\s|>))/i.test(content)) return 'html'
  if (/^<(?:style|script|canvas|main|section|article|header|footer|nav|aside|div|form|table|figure|h[1-6]|p|button)\b[\s\S]*<\/(?:[a-z][\w:-]*)>\s*$/i.test(content)) return 'html'
  return null
}

export function detectArtifactLanguage(artifact: PreviewArtifact): ArtifactLanguage {
  const metadata = metadataLanguage(artifact)
  if (metadata) return metadata
  const preview = getArtifactPreviewKind(artifact)
  if (preview) return preview === 'svg' ? 'xml' : 'html'
  const content = artifact.content.trim()
  if (/^[{[]/.test(content)) {
    try {
      JSON.parse(content)
      return 'json'
    } catch { /* A source expression may also start with a brace. */ }
  }
  if (/^(?:#!.*\bpython\b|(?:from\s+\S+\s+import|import\s+\w+(?:\s+as\s+\w+)?\s*$|(?:async\s+)?def\s+\w+\s*\()).*/m.test(content)) return 'python'
  if (/^(?:export\s+)?(?:interface\s+\w+|type\s+\w+\s*=)|\b(?:const|let)\s+\w+\s*:\s*\w+/m.test(content)) return 'typescript'
  if (/^(?:(?:export\s+)?(?:const|let|var|function)\s|import\s.+\sfrom\s|(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s)/m.test(content)) return 'javascript'
  if (/^(?:#!.*\b(?:ba|z|da)?sh\b|\$\s+|(?:npm|pnpm|pip|docker|cd|echo|export)\s)/m.test(content)) return 'bash'
  if (/^(?:SELECT\b[\s\S]+\bFROM\b|(?:CREATE|ALTER|DROP)\s+TABLE\b|INSERT\s+INTO\b|UPDATE\s+\S+\s+SET\b|WITH\s+\w+\s+AS\s*\()/i.test(content)) return 'sql'
  if (/^(?:[.#:@][\w-]|[a-z][\w-]*\s*\{)[\s\S]*\{?[^{}]*[\w-]+\s*:[^{}]+[;}]/i.test(content)) return 'css'
  if (artifact.type === 'report' || /^(?:#{1,6}\s|[-*]\s|```)|\[[^\]]+\]\([^)]+\)/m.test(content)) return 'markdown'
  return 'text'
}

export function buildArtifactSrcDoc(artifact: PreviewArtifact, kind: PreviewKind): string {
  // The iframe sandbox supplies origin isolation; CSP keeps preview resources local.
  const policy = `default-src 'none'; script-src ${kind === 'html' ? "'unsafe-inline'" : "'none'"}; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`
  const metadata = `<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}"><meta name="viewport" content="width=device-width, initial-scale=1">`
  if (kind === 'svg') {
    const svg = artifact.content.trim().replace(/^<\?xml[^>]*>\s*/i, '')
    return `<!doctype html><html><head>${metadata}<style>html,body{margin:0;min-height:100%;box-sizing:border-box}body{display:grid;place-items:center;padding:24px;background:#fff}svg{display:block;width:100%;max-width:100%;height:auto;max-height:100vh}</style></head><body>${svg}</body></html>`
  }

  let content = artifact.content.trim().replace(/^<!doctype[^>]*>\s*/i, '')
  const htmlTag = /^<html\b[^>]*>/i.exec(content)?.[0] ?? ''
  const lang = /\blang\s*=\s*["']([\w-]+)["']/i.exec(htmlTag)?.[1]
  const html = lang ? `<html lang="${lang}">` : '<html>'
  content = content.replace(/^<html\b[^>]*>\s*/i, '').replace(/<\/html>\s*$/i, '')
  const head = /^<head\b[^>]*>([\s\S]*?)<\/head>\s*/i.exec(content)
  const headContent = (head?.[1] ?? '').replace(/<meta\b(?=[^>]*(?:\bcharset\s*=|\bname\s*=\s*["']?viewport\b))[^>]*>/gi, '')
  if (head) content = content.slice(head[0].length)
  const body = /^<body\b/i.test(content) ? content : `<body>${content}</body>`
  return `<!doctype html>${html}<head>${metadata}${headContent}</head>${body}</html>`
}
