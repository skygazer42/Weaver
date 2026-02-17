'use client'

import { useState, memo } from 'react'
import Image from 'next/image'
import dynamic from 'next/dynamic'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { FileText, Code, BarChart, Download, Maximize2, Minimize2, PanelRightClose, PanelRightOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Artifact } from '@/types/chat'
import { InspectorEvidence } from './InspectorEvidence'

// Lazy-load ReactMarkdown + remarkGfm (heavy deps, not needed on first paint)
const ReactMarkdown = dynamic(() => import('react-markdown'), {
  ssr: false,
  loading: () => (
    <div className="space-y-3 p-4 animate-pulse">
      <div className="h-6 w-2/3 bg-muted/50 rounded" />
      <div className="h-4 w-full bg-muted/30 rounded" />
      <div className="h-4 w-5/6 bg-muted/30 rounded" />
      <div className="h-32 w-full bg-muted/20 rounded-lg mt-4" />
    </div>
  )
})
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './message/CodeBlock'

interface ArtifactsPanelProps {
  artifacts: Artifact[]
  threadId?: string | null
  isOpen?: boolean
  onToggle?: () => void
  toggleLabel?: string
  toggleTitle?: string
  allowFullscreen?: boolean
}

const ArtifactListItem = memo(function ArtifactListItem({
  artifact,
  isActive,
  onClick
}: {
  artifact: Artifact
  isActive: boolean
  onClick: () => void
}) {
  const icon = (() => {
    switch (artifact.type) {
      case 'report': return <FileText className="h-3.5 w-3.5" />
      case 'code': return <Code className="h-3.5 w-3.5" />
      case 'chart': return <BarChart className="h-3.5 w-3.5" />
      default: return <FileText className="h-3.5 w-3.5" />
    }
  })()

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={isActive ? 'true' : undefined}
      className={cn(
        "flex w-full items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors duration-200",
        isActive
          ? "bg-primary/10 border-primary/20 text-foreground"
          : "bg-transparent border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/50 hover:border-border/60"
      )}
      title={artifact.title}
    >
      <span className={cn("mt-0.5 shrink-0", isActive ? "text-primary" : "text-muted-foreground")}>
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-xs font-medium truncate", isActive && "text-foreground")}>
          {artifact.title}
        </span>
        <span className="block text-[11px] text-muted-foreground mt-0.5">
          {artifact.type}
        </span>
      </span>
    </button>
  )
})

export function ArtifactsPanel({
  artifacts,
  threadId = null,
  isOpen = true,
  onToggle,
  toggleLabel,
  toggleTitle,
  allowFullscreen = true,
}: ArtifactsPanelProps) {
  const hasArtifacts = artifacts.length > 0
  const hasEvidence = Boolean(threadId)

  const [isFullscreen, setIsFullscreen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [activeTab, setActiveTab] = useState<'artifacts' | 'evidence'>(() =>
    hasArtifacts ? 'artifacts' : 'evidence'
  )

  if (!hasArtifacts && !hasEvidence) return null

  // Ensure active index is valid
  const currentIndex = hasArtifacts ? Math.min(activeIndex, artifacts.length - 1) : 0
  const activeArtifact = hasArtifacts ? artifacts[currentIndex]! : null

  const renderTabs = (size: 'sm' | 'lg' = 'sm') => {
    const base = size === 'lg' ? 'h-9 text-sm' : 'h-8 text-xs'
    const padding = size === 'lg' ? 'px-3' : 'px-2.5'
    const countClass = size === 'lg' ? 'text-[11px]' : 'text-[10px]'

    return (
      <div
        role="tablist"
        aria-label="Inspector tabs"
        className="inline-flex rounded-lg border border-border/60 bg-muted/20 p-1"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'artifacts'}
          disabled={!hasArtifacts}
          onClick={() => setActiveTab('artifacts')}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md font-semibold transition-colors',
            base,
            padding,
            activeTab === 'artifacts'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground hover:bg-accent/40',
            !hasArtifacts && 'opacity-50 cursor-not-allowed hover:bg-transparent hover:text-muted-foreground'
          )}
        >
          <span>Artifacts</span>
          <span className={cn('tabular-nums text-muted-foreground', countClass)}>{artifacts.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'evidence'}
          disabled={!hasEvidence}
          onClick={() => setActiveTab('evidence')}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md font-semibold transition-colors',
            base,
            padding,
            activeTab === 'evidence'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground hover:bg-accent/40',
            !hasEvidence && 'opacity-50 cursor-not-allowed hover:bg-transparent hover:text-muted-foreground'
          )}
        >
          <span>Evidence</span>
        </button>
      </div>
    )
  }

  // If collapsed (and not fullscreen), render slim bar
  if (!isOpen && !isFullscreen) {
    return (
      <div className="h-full w-full border-l border-border/60 bg-card flex flex-col items-center py-3 gap-3 transition-colors duration-200">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onToggle}
          aria-label="Expand inspector"
          title="Expand inspector"
        >
          <PanelRightOpen className="h-5 w-5 text-muted-foreground" />
        </Button>
        <div className="flex-1 w-full flex flex-col items-center justify-center gap-2 overflow-hidden py-2">
          <div className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold text-muted-foreground tabular-nums">
            {hasArtifacts ? `A${artifacts.length}` : hasEvidence ? 'E' : '0'}
          </div>
          <div className="text-[10px] font-medium text-muted-foreground uppercase select-none">
            Inspector
          </div>
        </div>
      </div>
    )
  }

  // If fullscreen, render as a fixed overlay (show all artifacts)
  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-50 bg-background flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-border/60">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-8 w-8 bg-primary rounded-lg flex items-center justify-center text-primary-foreground font-semibold">
              I
            </div>
            <h2 className="text-lg font-semibold">Inspector</h2>
            <div className="hidden sm:block">
              {renderTabs('lg')}
            </div>
          </div>
          <Button type="button" variant="ghost" onClick={() => setIsFullscreen(false)}>
            <Minimize2 className="h-5 w-5 mr-2" />
            Close
          </Button>
        </div>
        <ScrollArea className="flex-1 p-8">
          {activeTab === 'evidence' ? (
            <div className="max-w-4xl mx-auto">
              <InspectorEvidence threadId={threadId} />
            </div>
          ) : hasArtifacts ? (
            <div className="max-w-5xl mx-auto space-y-8">
              {artifacts.map((artifact) => (
                <ArtifactCard key={artifact.id} artifact={artifact} isFullscreen />
              ))}
            </div>
          ) : (
            <div className="max-w-3xl mx-auto rounded-lg border border-border/60 bg-muted/10 p-6">
              <div className="text-sm font-semibold text-foreground">No artifacts yet</div>
              <div className="mt-1 text-sm text-muted-foreground text-pretty">
                Run a task that produces a report, code, or chart to see artifacts here.
              </div>
            </div>
          )}
        </ScrollArea>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-card border-l border-border/60 transition-colors duration-200 w-full">
      <div className="flex items-center justify-between p-4 border-b border-border/60 bg-background">
        <div className="flex items-center gap-2 min-w-0">
          {onToggle && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7 -ml-2"
              onClick={onToggle}
              aria-label={toggleLabel || 'Collapse inspector'}
              title={toggleTitle || 'Collapse inspector'}
            >
              <PanelRightClose className="h-4 w-4" />
            </Button>
          )}
          <div className="min-w-0">
            <h2 className="text-sm font-semibold truncate">Inspector</h2>
            <p className="text-xs text-muted-foreground truncate">
              {activeTab === 'evidence'
                ? 'Evidence view'
                : `${artifacts.length} artifact${artifacts.length === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {renderTabs('sm')}
          {allowFullscreen && activeTab === 'artifacts' && hasArtifacts ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setIsFullscreen(true)}
              aria-label="Open inspector fullscreen"
              title="Open fullscreen"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex">
        {activeTab === 'artifacts' && artifacts.length > 1 ? (
          <div className="w-[176px] shrink-0 border-r border-border/60 bg-muted/10">
            <ScrollArea className="h-full">
              <div className="p-2 space-y-1">
                {artifacts.map((artifact, index) => (
                  <ArtifactListItem
                    key={artifact.id}
                    artifact={artifact}
                    isActive={index === currentIndex}
                    onClick={() => setActiveIndex(index)}
                  />
                ))}
              </div>
            </ScrollArea>
          </div>
        ) : null}

        <ScrollArea className="flex-1 min-w-0">
          <div className="p-4">
            {activeTab === 'evidence' ? (
              <InspectorEvidence threadId={threadId} />
            ) : (
              <ArtifactPreview artifact={activeArtifact} />
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

function ArtifactPreview({ artifact }: { artifact: Artifact | null }) {
  if (!artifact) {
    return (
      <div className="rounded-lg border border-border/60 bg-muted/10 p-4">
        <div className="text-xs font-semibold text-foreground">No artifacts yet</div>
        <div className="mt-1 text-xs text-muted-foreground text-pretty">
          Run a task that produces a report, code, or chart to see artifacts here.
        </div>
      </div>
    )
  }

  const icon = (() => {
    switch (artifact.type) {
      case 'report': return <FileText className="h-4 w-4 text-primary" />
      case 'code': return <Code className="h-4 w-4 text-primary" />
      case 'chart': return <BarChart className="h-4 w-4 text-primary" />
      default: return <FileText className="h-4 w-4 text-primary" />
    }
  })()

  return (
    <div className="overflow-hidden rounded-lg border border-border/60 bg-background shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-border/60 bg-muted/20 px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex size-8 items-center justify-center rounded-md border border-border/60 bg-background">
            {icon}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold truncate">{artifact.title}</div>
            <div className="text-[11px] text-muted-foreground">{artifact.type}</div>
          </div>
        </div>
        {artifact.type === 'chart' ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8"
            aria-label="Download chart"
            title="Download chart"
          >
            <Download className="h-3.5 w-3.5" />
          </Button>
        ) : null}
      </div>

      <div className="p-3">
        {artifact.type === 'chart' && artifact.image ? (
          <div className="relative">
            <Image
              src={`data:image/png;base64,${artifact.image}`}
              alt={artifact.title}
              width={1400}
              height={900}
              unoptimized
              className="w-full object-contain bg-white rounded-md border border-border/60"
              sizes="(max-width: 1024px) 100vw, 600px"
              loading="lazy"
            />
          </div>
        ) : artifact.type === 'code' ? (
          <CodeBlock language="python" value={artifact.content} />
        ) : (
          <div className="prose dark:prose-invert max-w-none leading-relaxed prose-sm">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                pre: ({ children }) => <>{children}</>,
                code: ({ node, className, children, ...props }: any) => {
                  const match = /language-(\w+)/.exec(className || '')
                  const isInline = !match && !String(children).includes('\n')
                  const content = String(children).replace(/\n$/, '')
                  if (isInline) {
                    return (
                      <code className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono" {...props}>
                        {children}
                      </code>
                    )
                  }
                  return (
                    <CodeBlock language={match?.[1] ?? 'text'} value={content} />
                  )
                }
              }}
            >
              {artifact.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}

function ArtifactCard({ artifact, isFullscreen }: { artifact: Artifact, isFullscreen?: boolean }) {
  const getIcon = () => {
    switch (artifact.type) {
      case 'report': return <FileText className="h-4 w-4 text-primary" />
      case 'code': return <Code className="h-4 w-4 text-primary" />
      case 'chart': return <BarChart className="h-4 w-4 text-primary" />
      default: return <FileText className="h-4 w-4" />
    }
  }

  return (
    <Card className={cn(
      "overflow-hidden border-border/60 group transition-colors duration-200 hover:border-border/80",
      isFullscreen ? "shadow-md" : undefined
    )}>
      <CardHeader className="p-3 bg-muted/20 border-b border-border/60 flex flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="p-1.5 bg-background rounded-md shadow-sm">
            {getIcon()}
          </div>
          <CardTitle className={cn("font-semibold truncate", isFullscreen ? "text-base" : "text-xs")} title={artifact.title}>
            {artifact.title}
          </CardTitle>
        </div>
        {artifact.type === 'chart' && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity duration-200"
            aria-label="Download chart"
            title="Download chart"
          >
            <Download className="h-3 w-3" />
          </Button>
        )}
      </CardHeader>

      <CardContent className={cn("p-0 text-xs", artifact.type === 'report' ? "p-3 bg-background" : "bg-background")}>
        {artifact.type === 'chart' && artifact.image ? (
          <div className="relative group/image">
            <div className="absolute inset-0 bg-black/0 group-hover/image:bg-black/5 transition-colors" />
            <Image
              src={`data:image/png;base64,${artifact.image}`}
              alt={artifact.title}
              width={1400}
              height={900}
              unoptimized
              className={cn("w-full object-contain bg-white", isFullscreen ? "h-auto max-h-[600px]" : "h-auto")}
              sizes="(max-width: 1024px) 100vw, 600px"
              loading="lazy"
            />
          </div>
        ) : artifact.type === 'code' ? (
          <div className="p-2">
            <CodeBlock language="python" value={artifact.content} />
          </div>
        ) : (
          <div className={cn("prose dark:prose-invert max-w-none leading-relaxed", isFullscreen ? "prose-base p-6" : "prose-xs p-3")}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                pre: ({ children }) => <>{children}</>,
                code: ({ node, className, children, ...props }: any) => {
                  const match = /language-(\w+)/.exec(className || '')
                  const isInline = !match && !String(children).includes('\n')
                  const content = String(children).replace(/\n$/, '')
                  if (isInline) {
                    return (
                      <code className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono" {...props}>
                        {children}
                      </code>
                    )
                  }
                  return (
                    <CodeBlock language={match?.[1] ?? 'text'} value={content} />
                  )
                }
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
