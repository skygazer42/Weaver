'use client'

import React from 'react'
import { Artifact } from '@/types/chat'
import { FileText, Code, BarChart, Image as ImageIcon, File, MoreVertical, Trash2, Download, Clock } from 'lucide-react'
import { formatRelativeTime, formatBytes } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

interface ArtifactItemProps {
  artifact: Artifact
  onDelete: (id: string) => void
  onDownload?: (artifact: Artifact) => void
}

export function ArtifactItem({ artifact, onDelete, onDownload }: ArtifactItemProps) {
  const Icon = {
    code: Code,
    image: ImageIcon,
    text: FileText,
    file: File,
    report: FileText,
    chart: BarChart,
    tool_output: FileText,
  }[artifact.type] || File

  return (
    <div className="group relative rounded-lg border border-border/80 bg-card p-4 shadow-surface transition-colors hover:border-primary/40">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-subtle">
              <Icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <h3 className="truncate text-sm font-semibold" title={artifact.title}>
              {artifact.title}
            </h3>
          </div>
          
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-3 text-xs tabular-nums text-muted-foreground">
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatRelativeTime(artifact.createdAt)}
              </div>
              {artifact.fileSize && (
                <span>{formatBytes(artifact.fileSize)}</span>
              )}
            </div>
            <Badge variant="subtle">
              {artifact.type}
            </Badge>
          </div>
        </div>

        <div onClick={(e) => e.stopPropagation()}>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Artifact actions" className="h-8 w-8 opacity-70 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-40 p-1" align="end">
              <Button variant="ghost" className="w-full justify-start text-sm h-9" onClick={() => onDownload?.(artifact)}>
                <Download className="mr-2 h-4 w-4" /> Download
              </Button>
              <Button variant="ghost" className="w-full justify-start text-sm h-9 text-destructive hover:text-destructive" onClick={() => onDelete(artifact.id)}>
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </Button>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  )
}
