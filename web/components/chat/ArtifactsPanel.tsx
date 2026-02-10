'use client'

import React, { useState, memo } from 'react'
import Image from 'next/image'
import dynamic from 'next/dynamic'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { FileText, Code, BarChart, Download, Maximize2, Minimize2, ChevronRight, ChevronLeft, PanelRightClose, PanelRightOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Artifact } from '@/types/chat'

// Lazy-load ReactMarkdown + remarkGfm (heavy deps, not needed on first paint)
const ReactMarkdown = dynamic(() => import('react-markdown'), { ssr: false })
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './message/CodeBlock'

interface ArtifactsPanelProps {
  artifacts: Artifact[]
  isOpen?: boolean
  onToggle?: () => void
}

// Tab button component
const ArtifactTab = memo(function ArtifactTab({
  artifact,
  isActive,
  onClick
}: {
  artifact: Artifact
  isActive: boolean
  onClick: () => void
}) {
  const getTabIcon = () => {
    switch (artifact.type) {
      case 'report': return <FileText className="h-3 w-3" />
      case 'code': return <Code className="h-3 w-3" />
      case 'chart': return <BarChart className="h-3 w-3" />
      default: return <FileText className="h-3 w-3" />
    }
  }

  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap",
        isActive
          ? "bg-primary text-primary-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground hover:bg-muted"
      )}
      title={artifact.title}
    >
      {getTabIcon()}
      <span className="max-w-[80px] truncate">{artifact.title}</span>
    </button>
  )
})

export function ArtifactsPanel({ artifacts, isOpen = true, onToggle }: ArtifactsPanelProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  if (artifacts.length === 0) return null

  // Ensure active index is valid
  const currentIndex = Math.min(activeIndex, artifacts.length - 1)
  const activeArtifact = artifacts[currentIndex]

  // If collapsed (and not fullscreen), render slim bar
  if (!isOpen && !isFullscreen) {
    return (
      <div className="h-full w-[50px] border-l bg-muted/30 flex flex-col items-center py-4 gap-4 backdrop-blur-sm transition-all duration-300">
        <Button variant="ghost" size="icon" onClick={onToggle} title="Expand Artifacts">
          <PanelRightOpen className="h-5 w-5 text-muted-foreground" />
        </Button>
        <div className="flex-1 w-full flex flex-col items-center gap-2 overflow-hidden py-2">
          <div className="writing-mode-vertical text-xs font-semibold text-muted-foreground tracking-widest uppercase rotate-180 select-none">
            Artifacts ({artifacts.length})
          </div>
        </div>
      </div>
    )
  }

  // If fullscreen, render as a fixed overlay (show all artifacts)
  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-xl flex flex-col animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 bg-primary rounded-lg flex items-center justify-center text-primary-foreground font-bold">
              A
            </div>
            <h2 className="text-lg font-bold">Artifacts Viewer</h2>
          </div>
          <Button variant="ghost" onClick={() => setIsFullscreen(false)}>
            <Minimize2 className="h-5 w-5 mr-2" />
            Close
          </Button>
        </div>
        <ScrollArea className="flex-1 p-8">
          <div className="max-w-5xl mx-auto space-y-8">
            {artifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} isFullscreen />
            ))}
          </div>
        </ScrollArea>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-muted/30 border-l backdrop-blur-sm transition-all duration-300 w-full">
      <div className="flex items-center justify-between p-4 border-b bg-background/50">
        <div className="flex items-center gap-2">
          {onToggle && (
            <Button variant="ghost" size="icon" className="h-7 w-7 -ml-2" onClick={onToggle} title="Collapse">
              <PanelRightClose className="h-4 w-4" />
            </Button>
          )}
          <div>
            <h2 className="text-sm font-bold tracking-tight">Artifacts</h2>
            <p className="text-xs text-muted-foreground">{artifacts.length} generated</p>
          </div>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setIsFullscreen(true)}>
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Tab navigation for multiple artifacts */}
      {artifacts.length > 1 && (
        <div className="px-3 py-2 border-b bg-muted/20 overflow-x-auto">
          <div className="flex gap-1 min-w-max">
            {artifacts.map((artifact, index) => (
              <ArtifactTab
                key={artifact.id}
                artifact={artifact}
                isActive={index === currentIndex}
                onClick={() => setActiveIndex(index)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Only render the active artifact */}
      <ScrollArea className="flex-1 p-4">
        <div className="pb-4">
          <ArtifactCard artifact={activeArtifact} />
        </div>
      </ScrollArea>
    </div>
  )
}

function ArtifactCard({ artifact, isFullscreen }: { artifact: Artifact, isFullscreen?: boolean }) {
  const getIcon = () => {
    switch (artifact.type) {
      case 'report': return <FileText className="h-4 w-4 text-orange-500" />
      case 'code': return <Code className="h-4 w-4 text-blue-500" />
      case 'chart': return <BarChart className="h-4 w-4 text-green-500" />
      default: return <FileText className="h-4 w-4" />
    }
  }

  return (
    <Card className={cn(
      "overflow-hidden border-none shadow-sm ring-1 ring-border/50 group hover:ring-primary/20 transition-all",
      isFullscreen ? "shadow-md" : ""
    )}>
      <CardHeader className="p-3 bg-muted/30 border-b flex flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="p-1.5 bg-background rounded-md shadow-sm">
            {getIcon()}
          </div>
          <CardTitle className={cn("font-semibold truncate", isFullscreen ? "text-base" : "text-xs")} title={artifact.title}>
            {artifact.title}
          </CardTitle>
        </div>
        {artifact.type === 'chart' && (
          <Button variant="ghost" size="icon" className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity">
            <Download className="h-3 w-3" />
          </Button>
        )}
      </CardHeader>

      <CardContent className={cn("p-0 text-xs", artifact.type === 'report' ? "p-3 bg-background" : "bg-zinc-950")}>
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
                    <CodeBlock language={match ? match[1] : 'text'} value={content} />
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
