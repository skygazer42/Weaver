'use client'

import React from 'react'
import { Artifact } from '@/types/chat'
import { FileText, Code, Image as ImageIcon, File, MoreVertical, Trash2, Download, Clock } from 'lucide-react'
import { formatRelativeTime, formatBytes } from '@/lib/utils'
import { Button } from '@/components/ui/button'
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
    file: File
  }[artifact.type] || File

  return (
    <div className="group relative p-4 rounded-xl border bg-card hover:bg-muted/50 transition-all cursor-pointer">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
              <Icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <h3 className="font-semibold text-sm truncate">
              {artifact.title}
            </h3>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatRelativeTime(artifact.createdAt)}
              </div>
              {artifact.fileSize && (
                <span>{formatBytes(artifact.fileSize)}</span>
              )}
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground/50">
              {artifact.type}
            </span>
          </div>
        </div>

        <div onClick={(e) => e.stopPropagation()}>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
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
