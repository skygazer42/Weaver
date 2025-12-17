'use client'

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText, Code, BarChart } from 'lucide-react'

export interface Artifact {
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
  if (artifacts.length === 0) {
    return null
  }

  return (
    <div className="h-full border-l bg-muted/10">
      <div className="p-4 border-b">
        <h2 className="text-lg font-semibold">Artifacts</h2>
        <p className="text-sm text-muted-foreground">
          Generated content and visualizations
        </p>
      </div>

      <ScrollArea className="h-[calc(100%-80px)]">
        <div className="p-4 space-y-4">
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
      case 'report':
        return <FileText className="h-5 w-5" />
      case 'code':
        return <Code className="h-5 w-5" />
      case 'chart':
        return <BarChart className="h-5 w-5" />
      default:
        return <FileText className="h-5 w-5" />
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {getIcon()}
          {artifact.title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {artifact.type === 'chart' && artifact.image ? (
          <img
            src={`data:image/png;base64,${artifact.image}`}
            alt={artifact.title}
            className="w-full rounded-lg"
          />
        ) : artifact.type === 'code' ? (
          <pre className="bg-muted p-4 rounded-lg overflow-x-auto text-sm">
            <code>{artifact.content}</code>
          </pre>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {artifact.content}
            </ReactMarkdown>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
