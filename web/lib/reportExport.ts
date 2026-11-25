import { micromark } from 'micromark'
import { gfm, gfmHtml } from 'micromark-extension-gfm'
import { translations, type Language } from '@/lib/i18n/translations'

export function escapeMarkup(value: string) {
  const entities: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
  return value.replace(/[&<>"']/g, character => entities[character])
}

const editorialCss = `
  :root{color-scheme:light dark;--page:#f3f6fb;--paper:#fff;--ink:#182438;--muted:#506179;--rule:#dae3f0;--accent:#2557bf;--code:#eef3fa}
  @media(prefers-color-scheme:dark){:root{--page:#111929;--paper:#172132;--ink:#e9eff9;--muted:#a8b8d1;--rule:#34435c;--accent:#91b4ff;--code:#111a2a}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--page);color:var(--ink);font:16px/1.65 Inter,system-ui,sans-serif;overflow-wrap:anywhere}
  h1,h2,h3{font-family:Georgia,serif;line-height:1.13;letter-spacing:-.025em;text-wrap:balance}
  h1{font-size:clamp(2rem,5vw,3.6rem);margin:0 0 .65em}h2{font-size:clamp(1.45rem,3vw,2.4rem);margin:1.3em 0 .55em}h3{font-size:1.25rem}
  a{color:var(--accent);text-underline-offset:.18em}img{max-width:100%;height:auto}
  ul,ol{padding-inline-start:1.5em}li+li{margin-top:.35em}blockquote{margin-inline:0;border-inline-start:3px solid var(--rule);padding-inline:1em;color:var(--muted)}
  code{font-family:ui-monospace,Consolas,monospace;background:var(--code);border-radius:.25em;padding:.15em .35em}
  pre{overflow:auto;background:var(--code);padding:1rem;border-radius:.5rem;font-size:.9em}pre code{padding:0}
  table{border-collapse:collapse;width:100%;font-size:.92em}th,td{padding:.55em .7em;border-bottom:1px solid var(--rule);text-align:start}th{background:var(--code)}
  hr{border:0;border-top:1px solid var(--rule)}
`

function renderMarkdown(markdown: string) {
  return micromark(markdown, { extensions: [gfm()], htmlExtensions: [gfmHtml()] })
}

function documentHtml(title: string, locale: Language, styles: string, body: string, scripts = false) {
  const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; base-uri 'none'; form-action 'none'; script-src " + (scripts ? "'unsafe-inline'" : "'none'")
  return `<!doctype html><html lang="${locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="${policy}"><title>${escapeMarkup(title)}</title><style>${editorialCss}${styles}</style></head><body>${body}</body></html>`
}

export function buildStandaloneHtmlReport(title: string, markdown: string, locale: Language = 'en'): string {
  const content = renderMarkdown(markdown)
  const heading = /^<h1>/.test(content) ? '' : `<h1>${escapeMarkup(title)}</h1>`
  return documentHtml(title, locale, `
    main{max-width:64rem;margin:clamp(0px,4vw,3rem) auto;padding:clamp(1.4rem,6vw,5rem);background:var(--paper)}
    @media print{:root{color-scheme:light;--paper:#fff;--page:#fff;--ink:#000;--muted:#333;--rule:#bbb;--code:#eee;--accent:#123b80}main{margin:0;padding:0;max-width:none}h2,h3{break-after:avoid}pre{white-space:pre-wrap}tr,img{break-inside:avoid}}
  `, `<main>${heading}${content}</main>`)
}

export function buildInteractiveSlidesHtml(title: string, markdown: string, locale: Language = 'en'): string {
  const labels = translations[locale]
  const html = renderMarkdown(markdown)
  const parts: string[] = []
  let start = 0
  let depth = 0
  // Markdown can emit headings inside quotes and lists. Only top-level headings start slides.
  for (const { 0: tag, index } of html.matchAll(/^<\/?(?:blockquote|ul|ol)(?: [^>]*)?>|^<h2>/gm)) {
    if (tag === '<h2>') {
      if (depth !== 0) continue
      parts.push(html.slice(start, index))
      start = index
    } else {
      depth += tag.startsWith('</') ? -1 : 1
    }
  }
  parts.push(html.slice(start))
  const [intro, ...sections] = parts
  const cover = /^<h1>/.test(intro) ? intro : `<h1>${escapeMarkup(title)}</h1>${intro}`
  const slides = [cover, ...sections].map((content, index) =>
    `<section class="slide"${index ? ' hidden' : ''}>${content}</section>`).join('')
  return documentHtml(title, locale, `
    body{min-height:100dvh;display:grid;grid-template-rows:minmax(0,1fr) auto;gap:1rem;padding:clamp(.75rem,3vw,2rem);height:100dvh}
    main{display:flex;min-height:0;width:min(100%,78rem);margin:auto;align-self:stretch;height:100%;background:var(--paper);border:1px solid var(--rule);border-radius:1rem}
    .slide{width:100%;overflow:auto;padding:clamp(1.25rem,7vw,6rem);font-size:clamp(1rem,2vw,1.25rem)}
    .slide>:first-child{margin-top:0}.slide h2{color:var(--accent)}
    nav{display:flex;justify-content:center;align-items:center;gap:1rem;color:var(--muted);font-size:.85rem;font-variant-numeric:tabular-nums}
    button{font:inherit;padding:.48rem .95rem;border:1px solid var(--rule);border-radius:.5rem;background:var(--paper);color:var(--ink);cursor:pointer}
    button:disabled{opacity:.55;cursor:default}button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
    @media print{body,main{display:block;height:auto;padding:0;border:0}.slide[hidden]{display:block}.slide{break-after:page;overflow:visible}nav{display:none}}
  `, `<main>${slides}</main>
    <nav aria-label="${labels.studioSlidesNavigation}"><button id="previous" type="button" disabled>${labels.studioSlidesPrevious}</button><output aria-live="polite">1 / ${sections.length + 1}</output><button id="next" type="button"${sections.length ? '' : ' disabled'}>${labels.studioSlidesNext}</button></nav>
    <script>
      const slides = document.querySelectorAll('.slide');
      const previous = document.getElementById('previous');
      const next = document.getElementById('next');
      const counter = document.querySelector('output');
      let index = 0;
      function move(step) {
        const target = Math.max(0, Math.min(slides.length - 1, index + step));
        if (target === index) return;
        slides[index].hidden = true;
        index = target;
        slides[index].hidden = false;
        counter.textContent = (index + 1) + ' / ' + slides.length;
        previous.disabled = index === 0;
        next.disabled = index === slides.length - 1;
      }
      previous.addEventListener('click', () => move(-1));
      next.addEventListener('click', () => move(1));
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && window.parent !== window) window.parent.postMessage('weaver:close-slides', '*');
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        move(event.key === 'ArrowLeft' ? -1 : 1);
      });
    </script>`, true)
}
