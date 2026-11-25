'use client'

import React, { useEffect, useId, useRef, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText, Code, BarChart, Download, Maximize2, PanelRightClose, PanelRightOpen, Check, Copy, RotateCw, ShieldCheck, Terminal, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Artifact } from '@/types/chat'
import { CodeBlock } from './message/CodeBlock'
import { getApiBaseUrl, getArtifactDownloadUrl } from '@/lib/api'
import { buildArtifactSrcDoc, detectArtifactLanguage, getArtifactPreviewKind } from '@/lib/artifactPreview'
import { downloadBlob, downloadName } from '@/lib/download'
import { buildInteractiveSlidesHtml, buildStandaloneHtmlReport } from '@/lib/reportExport'
import { useI18n } from '@/lib/i18n/i18n-context'
import { toast } from 'sonner'

interface ArtifactsPanelProps {
  artifacts: Artifact[]
  isOpen?: boolean
  onToggle?: () => void
  embedded?: boolean
  threadId?: string | null
}

export function ArtifactsPanel({ artifacts, isOpen = true, onToggle, embedded = false, threadId }: ArtifactsPanelProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)
  const { t } = useI18n()
  const latestReport = artifacts.findLast(artifact => artifact.type === 'report')

  if (artifacts.length === 0) return null

  if (!isOpen && !isFullscreen) {
    return (
      <div className="flex h-full w-[50px] flex-col items-center gap-4 border-l border-border/80 bg-surface-subtle pt-3">
        <Button type="button" variant="ghost" size="icon" onClick={onToggle} aria-label={t('expandArtifacts')}>
          <PanelRightOpen className="h-4 w-4 text-muted-foreground" />
        </Button>
        <div className="select-none py-2 text-[11px] font-semibold uppercase tracking-wider tabular-nums text-muted-foreground [writing-mode:vertical-rl]">
          {t('artifactsTitle')} ({artifacts.length})
        </div>
      </div>
    )
  }

  return (
    <>
      <section aria-label={t('artifactsTitle')} className={cn('flex h-full w-full flex-col bg-surface-subtle', !embedded && 'border-l border-border/80')}>
        <div className={cn('flex shrink-0 items-center gap-3', embedded ? 'justify-end px-4 pt-2' : 'h-14 justify-between border-b border-border/80 px-4')}>
          {!embedded && <div className="flex min-w-0 items-center gap-2">
            {onToggle && (
              <Button type="button" variant="ghost" size="icon" className="-ml-2 text-muted-foreground" onClick={onToggle} aria-label={t('collapseArtifacts')}>
                <PanelRightClose className="h-4 w-4" />
              </Button>
            )}
            <h2 className="text-sm font-semibold tracking-tight">{t('artifactsTitle')}</h2>
            <span className="rounded border border-border/80 bg-card px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">{artifacts.length}</span>
          </div>}
          <Button type="button" variant="ghost" size={embedded ? 'sm' : 'icon'} onClick={() => setIsFullscreen(true)} aria-label={t('artifactsFullscreen')} title={t('artifactsFullscreen')} className="gap-1.5 text-muted-foreground">
            <Maximize2 className="h-4 w-4" />
            {embedded && t('artifactsFullscreen')}
          </Button>
        </div>

        <ScrollArea className={cn('min-h-0 flex-1 p-4', embedded && 'pt-1')}>
          <div className="space-y-4 pb-4">
            {artifacts.map(artifact => <ArtifactCard key={artifact.id} artifact={artifact} threadId={artifact === latestReport ? threadId : undefined} />)}
          </div>
        </ScrollArea>
      </section>

      <Dialog open={isFullscreen} onOpenChange={setIsFullscreen}>
        <DialogContent closeLabel={t('closeArtifactsViewer')} className="flex h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-none flex-col gap-0 overflow-hidden bg-surface-subtle p-0">
          <DialogHeader className="flex h-14 shrink-0 justify-center space-y-0 border-b border-border/80 px-5 pr-14">
            <DialogTitle className="text-sm">{t('artifactsViewer')}</DialogTitle>
            <DialogDescription className="sr-only">{t('artifactsDescription')}</DialogDescription>
          </DialogHeader>
          <section aria-label={t('artifactsTitle')} className="min-h-0 flex-1 overflow-hidden">
            <ScrollArea className="h-full p-4 sm:p-8">
              <div className="mx-auto max-w-5xl space-y-6">
                {artifacts.map(artifact => <ArtifactCard key={artifact.id} artifact={artifact} threadId={artifact === latestReport ? threadId : undefined} isFullscreen />)}
              </div>
            </ScrollArea>
          </section>
        </DialogContent>
      </Dialog>
    </>
  )
}

function ArtifactCard({ artifact, isFullscreen, threadId }: { artifact: Artifact; isFullscreen?: boolean; threadId?: string | null }) {
  const { t } = useI18n()
  const [view, setView] = useState<'preview' | 'code'>('preview')
  const [reloadCount, setReloadCount] = useState(0)
  const [copied, setCopied] = useState(false)
  const [outputExpanded, setOutputExpanded] = useState(false)
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const outputId = useId()
  useEffect(() => () => { if (copyTimer.current) clearTimeout(copyTimer.current) }, [])

  const previewKind = getArtifactPreviewKind(artifact)
  const language = detectArtifactLanguage(artifact)
  const downloadUrl = getArtifactDownloadUrl(artifact.download_url)
  const Icon = artifact.type === 'tool_output' ? Terminal : artifact.type === 'code' ? Code : artifact.type === 'chart' ? BarChart : FileText
  const outputLines = artifact.content.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n')
  const lineCount = artifact.content ? outputLines.length : 0
  const lineLabel = t(lineCount === 1 ? 'artifactLine' : 'artifactLines').replace('{count}', String(lineCount))

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(artifact.content)
      setCopied(true)
      if (copyTimer.current) clearTimeout(copyTimer.current)
      copyTimer.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('artifactCopyFailed'))
    }
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="space-y-3 border-b border-border/70 bg-card p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground" />
            <CardTitle className={cn('truncate font-medium leading-snug', isFullscreen ? 'text-base' : 'text-sm')} title={artifact.title}>
              {artifact.title}
            </CardTitle>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {artifact.type === 'report' && <ReportExportMenu artifact={artifact} threadId={threadId} />}
            <Button type="button" variant="ghost" size="icon" onClick={handleCopy} aria-label={t(copied ? 'artifactCopied' : 'artifactCopy')} title={t(copied ? 'artifactCopied' : 'artifactCopy')} className="text-muted-foreground">
              {copied ? <Check aria-hidden="true" className="h-4 w-4 text-success" /> : <Copy aria-hidden="true" className="h-4 w-4" />}
            </Button>
            <span role="status" className="sr-only">{copied ? t('artifactCopied') : ''}</span>
            {downloadUrl && (
              <Button asChild variant="ghost" size="icon" className="shrink-0 text-muted-foreground">
                <a href={downloadUrl} download aria-label={`${t('download')} ${artifact.title}`} title={`${t('download')} ${artifact.title}`}>
                  <Download aria-hidden="true" className="h-4 w-4" />
                </a>
              </Button>
            )}
          </div>
        </div>
        {previewKind && (
          <div className="flex items-center justify-between gap-3">
            <div role="group" aria-label={t('artifactView')} className="inline-flex gap-0.5 rounded-md border border-border/80 bg-surface-subtle p-0.5">
              {(['preview', 'code'] as const).map(mode => (
                <Button key={mode} type="button" variant="ghost" size="sm" aria-pressed={view === mode} onClick={() => setView(mode)} className={cn('h-7 px-3 text-xs text-muted-foreground', view === mode && 'bg-card text-foreground shadow-xs hover:bg-card')}>
                  {t(mode === 'preview' ? 'artifactPreview' : 'artifactCode')}
                </Button>
              ))}
            </div>
            {view === 'preview' && (
              <Button type="button" variant="ghost" size="icon" onClick={() => setReloadCount(count => count + 1)} aria-label={t('reloadArtifactPreview')} title={t('reloadArtifactPreview')} className="text-muted-foreground">
                <RotateCw aria-hidden="true" className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        )}
      </CardHeader>

      <CardContent className="bg-card p-0 text-sm">
        {previewKind && view === 'preview' ? (
          <div className="bg-surface-subtle p-2">
            <iframe
              key={reloadCount}
              title={artifact.title}
              srcDoc={buildArtifactSrcDoc(artifact, previewKind)}
              sandbox={previewKind === 'html' ? 'allow-scripts' : ''}
              referrerPolicy="no-referrer"
              className={cn('block w-full rounded-md border border-border/80 bg-white', isFullscreen ? 'h-[min(70dvh,680px)]' : 'h-[340px]')}
            />
            <p className="flex items-center gap-1.5 px-1 pb-0.5 pt-2 text-[11px] text-muted-foreground">
              <ShieldCheck aria-hidden="true" className="h-3.5 w-3.5" />{t('sandboxedArtifactPreview')}
            </p>
          </div>
        ) : artifact.type === 'chart' && artifact.image && !previewKind ? (
          <img
            src={`data:image/png;base64,${artifact.image}`}
            alt={artifact.title}
            className={cn('h-auto w-full bg-white object-contain', isFullscreen && 'max-h-[600px]')}
          />
        ) : artifact.type === 'tool_output' ? (
          <div className="bg-surface-subtle/60">
            <div className="flex items-center justify-between gap-3 border-b border-border/60 px-3.5 py-2 text-xs text-muted-foreground">
              <span className="font-mono tabular-nums">{lineLabel}</span>
              {lineCount > 16 && (
                <Button type="button" variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" aria-expanded={outputExpanded} aria-controls={outputId} onClick={() => setOutputExpanded(expanded => !expanded)}>
                  {t(outputExpanded ? 'collapseArtifactOutput' : 'expandArtifactOutput')}
                  {outputExpanded ? <ChevronUp aria-hidden="true" className="h-3.5 w-3.5" /> : <ChevronDown aria-hidden="true" className="h-3.5 w-3.5" />}
                </Button>
              )}
            </div>
            <pre id={outputId} className="whitespace-pre-wrap break-words p-3.5 font-mono text-xs leading-6 text-foreground">{outputExpanded ? artifact.content : outputLines.slice(0, 16).join('\n')}</pre>
          </div>
        ) : previewKind || artifact.type === 'code' ? (
          <div className="px-3"><CodeBlock language={language} value={artifact.content} showHeader={false} /></div>
        ) : (
          <div className={cn('prose max-w-none leading-relaxed', isFullscreen ? 'p-6' : 'p-3.5 text-sm')}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                pre: ({ children }) => <>{children}</>,
                code: ({ node, className, children, ...props }: any) => {
                  const match = /language-(\w+)/.exec(className || '')
                  const isInline = !match && !String(children).includes('\n')
                  const content = String(children).replace(/\n$/, '')
                  if (isInline) return <code className="whitespace-pre-wrap font-mono" {...props}>{children}</code>
                  return <CodeBlock language={match ? match[1] : 'text'} value={content} showHeader={false} />
                },
              }}
            >
              {artifact.content}
            </ReactMarkdown>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ReportExportMenu({ artifact, threadId }: { artifact: Artifact; threadId?: string | null }) {
  const { t, language } = useI18n()
  const [menuOpen, setMenuOpen] = useState(false)
  const [slidesPreview, setSlidesPreview] = useState<string>()
  const frame = useRef<HTMLIFrameElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const filename = downloadName(artifact.title, 'report')
  // The backend tags streamed reports with their original thread ID.
  const reportThreadId = /^report_(.+)$/.exec(artifact.id)?.[1] ?? threadId

  useEffect(() => {
    if (!slidesPreview) return
    const closeFromFrame = (event: MessageEvent) => {
      if (event.source === frame.current?.contentWindow && event.data === 'weaver:close-slides') setSlidesPreview(undefined)
    }
    window.addEventListener('message', closeFromFrame)
    return () => window.removeEventListener('message', closeFromFrame)
  }, [slidesPreview])

  const makeSlides = () => buildInteractiveSlidesHtml(artifact.title, artifact.content, language)
  const downloadHtml = (content: string, name: string) =>
    downloadBlob(new Blob([content], { type: 'text/html;charset=utf-8' }), name + '.html')

  async function downloadReport(format: 'html' | 'pdf' | 'docx') {
    const name = format === 'docx' ? 'Word' : format.toUpperCase()
    try {
      if (reportThreadId) {
        const response = await fetch(getApiBaseUrl() + '/api/export/' + encodeURIComponent(reportThreadId) + '?format=' + format)
        if (response.ok) {
          downloadBlob(await response.blob(), filename + '.' + format)
          return
        }
        if (format !== 'html' && response.status !== 404 && response.status !== 501) {
          toast.error(t('studioExportFailed'))
          return
        }
      }
      if (format !== 'html') {
        toast.error(t('studioExportUnavailable').replace('{format}', name))
        return
      }
    } catch {
      if (format !== 'html') {
        toast.error(t('studioExportFailed'))
        return
      }
    }
    downloadHtml(buildStandaloneHtmlReport(artifact.title, artifact.content, language), filename)
  }

  const actions = [
    { label: 'studioExportMarkdown', run: () => downloadBlob(new Blob([artifact.content], { type: 'text/markdown;charset=utf-8' }), filename + '.md') },
    { label: 'studioExportHtml', run: () => void downloadReport('html') },
    { label: 'studioPreviewSlides', run: () => setSlidesPreview(buildArtifactSrcDoc({ ...artifact, content: makeSlides() }, 'html')) },
    { label: 'studioDownloadSlides', run: () => downloadHtml(makeSlides(), filename + '-slides') },
    { label: 'studioExportPdf', run: () => void downloadReport('pdf') },
    { label: 'studioExportWord', run: () => void downloadReport('docx') },
  ] as const

  return (
    <>
      <Popover open={menuOpen} onOpenChange={setMenuOpen}>
        <PopoverTrigger asChild>
          <Button ref={trigger} type="button" variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-xs text-muted-foreground">
            <Download aria-hidden="true" className="size-3.5" />
            {t('studioReportExport')}
            <ChevronDown aria-hidden="true" className="size-3" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" aria-label={t('studioReportExport')} className="w-max min-w-44 max-w-[calc(100vw-2rem)] p-1.5">
          {actions.map(({ label, run }) => (
            <Button key={label} type="button" variant="ghost" size="sm" className={cn('h-auto min-h-8 w-full justify-start whitespace-normal px-2.5 py-1.5 text-left text-xs',
              label === 'studioPreviewSlides' && 'mt-0.5 border-t border-border text-primary',
              label === 'studioExportPdf' && 'mt-0.5 border-t border-border')} onClick={() => {
              setMenuOpen(false)
              run()
            }}>{t(label)}</Button>
          ))}
        </PopoverContent>
      </Popover>
      <Dialog open={Boolean(slidesPreview)} onOpenChange={open => { if (!open) setSlidesPreview(undefined) }}>
        {slidesPreview && <DialogContent closeLabel={t('studioClosePreview')} onCloseAutoFocus={event => {
          event.preventDefault()
          trigger.current?.focus()
        }} className="flex h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-none flex-col gap-0 overflow-hidden bg-card p-0 data-[state=open]:zoom-in-100 data-[state=closed]:zoom-out-100">
          <DialogHeader className="flex h-14 shrink-0 justify-center space-y-0 border-b border-border px-5 pr-14">
            <DialogTitle className="flex min-w-0 items-center gap-2 text-sm">
              <span className="shrink-0">{t('studioSlidesTitle')}</span>
              <span aria-hidden="true" className="text-muted-foreground">·</span>
              <span className="truncate font-normal text-muted-foreground">{artifact.title}</span>
            </DialogTitle>
            <DialogDescription className="sr-only">{t('sandboxedArtifactPreview')}</DialogDescription>
          </DialogHeader>
          <iframe ref={frame} title={t('studioSlidesTitle')} srcDoc={slidesPreview} sandbox="allow-scripts" referrerPolicy="no-referrer"
            onLoad={() => frame.current?.contentWindow?.focus()} className="block min-h-0 w-full flex-1 border-0 [color-scheme:light] dark:[color-scheme:dark]" />
        </DialogContent>}
      </Dialog>
    </>
  )
}
