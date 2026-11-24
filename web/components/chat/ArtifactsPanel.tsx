'use client'

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText, Code, BarChart, Download, Maximize2, PanelRightClose, PanelRightOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Artifact } from '@/types/chat'
import { CodeBlock } from './message/CodeBlock'
import { getArtifactDownloadUrl } from '@/lib/api'

interface ArtifactsPanelProps {
  artifacts: Artifact[]
  isOpen?: boolean
  onToggle?: () => void
}

export function ArtifactsPanel({ artifacts, isOpen = true, onToggle }: ArtifactsPanelProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)

  if (artifacts.length === 0) return null

  if (!isOpen && !isFullscreen) {
    return (
      <div className="flex h-full w-[50px] flex-col items-center gap-4 border-l border-border/80 bg-surface-subtle pt-3">
        <Button type="button" variant="ghost" size="icon" onClick={onToggle} aria-label="Expand artifacts">
          <PanelRightOpen className="h-4 w-4 text-muted-foreground" />
        </Button>
        <div className="select-none py-2 text-[11px] font-semibold uppercase tracking-wider tabular-nums text-muted-foreground [writing-mode:vertical-rl]">
          Artifacts ({artifacts.length})
        </div>
      </div>
    )
  }

  return (
    <>
      <section aria-label="Artifacts" className="flex h-full w-full flex-col border-l border-border/80 bg-surface-subtle">
        <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border/80 px-4">
          <div className="flex min-w-0 items-center gap-2">
            {onToggle && (
              <Button type="button" variant="ghost" size="icon" className="-ml-2 text-muted-foreground" onClick={onToggle} aria-label="Collapse artifacts">
                <PanelRightClose className="h-4 w-4" />
              </Button>
            )}
            <h2 className="text-sm font-semibold tracking-tight">Artifacts</h2>
            <span className="rounded border border-border/80 bg-card px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">{artifacts.length}</span>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={() => setIsFullscreen(true)} aria-label="Expand artifacts to fullscreen" className="text-muted-foreground">
            <Maximize2 className="h-4 w-4" />
          </Button>
        </div>

        <ScrollArea className="min-h-0 flex-1 p-4">
          <div className="space-y-4 pb-4">
            {artifacts.map(artifact => <ArtifactCard key={artifact.id} artifact={artifact} />)}
          </div>
        </ScrollArea>
      </section>

      <Dialog open={isFullscreen} onOpenChange={setIsFullscreen}>
        <DialogContent className="flex h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-none flex-col gap-0 overflow-hidden bg-surface-subtle p-0">
          <DialogHeader className="flex h-14 shrink-0 justify-center space-y-0 border-b border-border/80 px-5 pr-14">
            <DialogTitle className="text-sm">Artifacts Viewer</DialogTitle>
            <DialogDescription className="sr-only">Generated assets and research outputs</DialogDescription>
          </DialogHeader>
          <section aria-label="Artifacts" className="min-h-0 flex-1 overflow-hidden">
            <ScrollArea className="h-full p-4 sm:p-8">
              <div className="mx-auto max-w-5xl space-y-6">
                {artifacts.map(artifact => <ArtifactCard key={artifact.id} artifact={artifact} isFullscreen />)}
              </div>
            </ScrollArea>
          </section>
        </DialogContent>
      </Dialog>
    </>
  )
}

function ArtifactCard({ artifact, isFullscreen }: { artifact: Artifact, isFullscreen?: boolean }) {
  const downloadUrl = getArtifactDownloadUrl(artifact.download_url)
  const Icon = artifact.type === 'code' ? Code : artifact.type === 'chart' ? BarChart : FileText

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 border-b border-border/70 bg-card p-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="rounded-md border border-border/70 bg-surface-subtle p-1.5 text-muted-foreground">
            <Icon className="h-4 w-4" />
          </div>
          <CardTitle className={cn('truncate font-medium leading-snug', isFullscreen ? 'text-base' : 'text-sm')} title={artifact.title}>
            {artifact.title}
          </CardTitle>
        </div>
        {downloadUrl && (
          <Button asChild variant="ghost" size="icon" className="shrink-0 text-muted-foreground">
            <a href={downloadUrl} download aria-label={`Download ${artifact.title}`} title={`Download ${artifact.title}`}>
              <Download aria-hidden="true" className="h-4 w-4" />
            </a>
          </Button>
        )}
      </CardHeader>

      <CardContent className="bg-card p-0 text-sm">
        {artifact.type === 'chart' && artifact.image ? (
          <img
            src={`data:image/png;base64,${artifact.image}`}
            alt={artifact.title}
            className={cn('h-auto w-full bg-white object-contain', isFullscreen && 'max-h-[600px]')}
          />
        ) : artifact.type === 'tool_output' ? (
          <pre className="whitespace-pre-wrap break-words p-3.5 font-mono text-xs leading-6 text-foreground">{artifact.content}</pre>
        ) : artifact.type === 'code' ? (
          <div className="px-3"><CodeBlock language="python" value={artifact.content} /></div>
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
                  return <CodeBlock language={match ? match[1] : 'text'} value={content} />
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
