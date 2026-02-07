'use client'

import React, { memo } from 'react'
import Image from 'next/image'
import { X, File as FileIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AttachmentPreviewItem {
  file: File
  previewUrl: string
}

interface AttachmentPreviewProps {
  previews: AttachmentPreviewItem[]
  onRemove: (index: number) => void
  className?: string
}

const PreviewItem = memo(function PreviewItem({
  item,
  index,
  onRemove
}: {
  item: AttachmentPreviewItem
  index: number
  onRemove: (index: number) => void
}) {
  const isImage = item.file.type.startsWith('image/')

  return (
    <div className="relative group/attachment flex-shrink-0">
      <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-muted/50 border text-xs font-medium max-w-[200px] overflow-hidden">
        {isImage ? (
          <div className="h-8 w-8 rounded overflow-hidden flex-shrink-0 bg-background">
            <Image
              src={item.previewUrl}
              alt={`Preview of ${item.file.name}`}
              width={32}
              height={32}
              unoptimized
              className="h-full w-full object-cover"
            />
          </div>
        ) : (
          <div className="h-8 w-8 rounded bg-background flex items-center justify-center flex-shrink-0">
            <FileIcon className="h-4 w-4 text-orange-500" />
          </div>
        )}
        <span className="truncate flex-1" title={item.file.name}>
          {item.file.name}
        </span>
      </div>
      <button
        type="button"
        onClick={() => onRemove(index)}
        aria-label={`Remove ${item.file.name}`}
        className="absolute -top-1 -right-1 bg-background border rounded-full p-0.5 text-muted-foreground hover:text-destructive shadow-sm opacity-0 group-hover/attachment:opacity-100 transition-opacity"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
})

export function AttachmentPreview({ previews, onRemove, className }: AttachmentPreviewProps) {
  if (previews.length === 0) return null

  return (
    <div
      className={cn(
        "flex gap-2 px-14 pt-4 overflow-x-auto py-2 scrollbar-none",
        className
      )}
      role="list"
      aria-label="Attached files"
    >
      {previews.map((item, index) => (
        <PreviewItem
          key={`${item.file.name}-${index}`}
          item={item}
          index={index}
          onRemove={onRemove}
        />
      ))}
    </div>
  )
}
