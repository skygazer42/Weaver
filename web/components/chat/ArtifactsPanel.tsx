'use client'

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText, Code, BarChart, Download, X, Maximize2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface Artifact {
  id: string
  type: 'report' | 'code' | 'chart' | 'data'
  title: string
  content: string
  image?: string // Base64 encoded image
}

interface ArtifactsPanelProps {
  artifacts: Artifact[]
}

export function ArtifactsPanel({ artifacts }: ArtifactsPanelProps) {
  if (artifacts.length === 0) return null

  return (
    <div className="flex flex-col h-full bg-muted/30 border-l backdrop-blur-sm">
      <div className="flex items-center justify-between p-4 border-b bg-background/50">
        <div>
            <h2 className="text-sm font-bold tracking-tight">Artifacts</h2>
            <p className="text-xs text-muted-foreground">Generated assets & reports</p>
        </div>
        <div className="flex gap-1">
             {/* Placeholder actions */}
             <Button variant="ghost" size="icon" className="h-7 w-7"><Maximize2 className="h-3.5 w-3.5" /></Button>
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

function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const getIcon = () => {
    switch (artifact.type) {
      case 'report': return <FileText className="h-4 w-4 text-orange-500" />
      case 'code': return <Code className="h-4 w-4 text-blue-500" />
      case 'chart': return <BarChart className="h-4 w-4 text-green-500" />
      default: return <FileText className="h-4 w-4" />
    }
  }

  return (
    <Card className="overflow-hidden border-none shadow-sm ring-1 ring-border/50 group hover:ring-primary/20 transition-all">
      <CardHeader className="p-3 bg-muted/30 border-b flex flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2 overflow-hidden">
             <div className="p-1.5 bg-background rounded-md shadow-sm">
                {getIcon()}
             </div>
             <CardTitle className="text-xs font-semibold truncate" title={artifact.title}>
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
                className="w-full h-auto object-contain bg-white"
             />
          </div>
        ) : artifact.type === 'code' ? (
          <ScrollArea className="h-[200px] w-full">
            <pre className="p-3 font-mono text-[10px] text-zinc-300">
                <code>{artifact.content}</code>
            </pre>
          </ScrollArea>
        ) : (
          <div className="prose prose-xs dark:prose-invert max-w-none leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {artifact.content}
            </ReactMarkdown>
          </div>
        )}
      </CardContent>
    </Card>
  )
}