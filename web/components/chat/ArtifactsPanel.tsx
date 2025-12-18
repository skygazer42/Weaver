'use client'

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText, Code, BarChart, Download, Maximize2, Minimize2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Artifact } from '@/types/chat'

interface ArtifactsPanelProps {
  artifacts: Artifact[]
}

export function ArtifactsPanel({ artifacts }: ArtifactsPanelProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)

  if (artifacts.length === 0) return null

  // If fullscreen, render as a fixed overlay
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
    <div className="flex flex-col h-full bg-muted/30 border-l backdrop-blur-sm transition-all duration-300">
      <div className="flex items-center justify-between p-4 border-b bg-background/50">
        <div>
            <h2 className="text-sm font-bold tracking-tight">Artifacts</h2>
            <p className="text-xs text-muted-foreground">Generated assets</p>
        </div>
        <div className="flex gap-1">
             <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setIsFullscreen(true)}>
                 <Maximize2 className="h-3.5 w-3.5" />
             </Button>
        </div>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4 pb-4">
          {artifacts.map((artifact) => (
            <ArtifactCard key={artifact.id} artifact={artifact} />
          ))}
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
             <img
                src={`data:image/png;base64,${artifact.image}`}
                alt={artifact.title}
                className={cn("w-full object-contain bg-white", isFullscreen ? "h-auto max-h-[600px]" : "h-auto")}
             />
          </div>
        ) : artifact.type === 'code' ? (
          <ScrollArea className={cn("w-full", isFullscreen ? "h-[400px]" : "h-[200px]")}>
            <pre className={cn("font-mono text-zinc-300", isFullscreen ? "p-6 text-sm" : "p-3 text-[10px]")}>
                <code>{artifact.content}</code>
            </pre>
          </ScrollArea>
        ) : (
          <div className={cn("prose dark:prose-invert max-w-none leading-relaxed", isFullscreen ? "prose-base p-6" : "prose-xs p-3")}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {artifact.content}
            </ReactMarkdown>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
