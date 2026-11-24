'use client'

import React from 'react'
import { ChatSession } from '@/types/chat'
import { MessageSquare, MoreVertical, Pencil, Trash2, Pin, PinOff, Clock } from 'lucide-react'
import { cn, formatRelativeTime } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

interface SessionItemProps {
  session: ChatSession
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string) => void
  onTogglePin: (id: string) => void
}

export function SessionItem({ 
  session, 
  onSelect, 
  onDelete, 
  onRename, 
  onTogglePin 
}: SessionItemProps) {
  return (
    <div className={cn('group relative cursor-pointer rounded-lg border border-border/80 border-l-2 bg-card p-4 shadow-surface transition-colors hover:border-primary/40', session.isPinned ? 'border-l-primary' : 'border-l-transparent')}
         onClick={() => onSelect(session.id)}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <MessageSquare className="h-4 w-4 text-primary shrink-0" />
            <h3 className="min-w-0 flex-1 text-sm font-semibold">
              <button type="button" className="block w-full truncate rounded-sm text-left transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50" onClick={(event) => { event.stopPropagation(); onSelect(session.id) }} title={session.title}>
                {session.title}
              </button>
            </h3>
            {session.isPinned && <Badge variant="subtle" className="shrink-0">Pinned</Badge>}
          </div>
          
          <p className="text-sm text-muted-foreground line-clamp-1 mb-3">
            {session.summary || "No summary available"}
          </p>
          
          <div className="flex flex-wrap items-center gap-2">
            <div className="mr-2 flex items-center gap-1 text-xs tabular-nums text-muted-foreground">
              <Clock className="h-3 w-3" />
              {formatRelativeTime(session.updatedAt)}
            </div>
            {session.tags?.map(tag => (
              <Badge key={tag} variant="subtle">
                {tag}
              </Badge>
            ))}
          </div>
        </div>

        <div onClick={(e) => e.stopPropagation()}>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Session actions" className="h-8 w-8 opacity-70 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-40 p-1" align="end">
              <Button variant="ghost" className="w-full justify-start text-sm h-9" onClick={() => onTogglePin(session.id)}>
                {session.isPinned ? <PinOff className="mr-2 h-4 w-4" /> : <Pin className="mr-2 h-4 w-4" />}
                {session.isPinned ? 'Unpin' : 'Pin'}
              </Button>
              <Button variant="ghost" className="w-full justify-start text-sm h-9" onClick={() => onRename(session.id)}>
                <Pencil className="mr-2 h-4 w-4" /> Rename
              </Button>
              <Button variant="ghost" className="w-full justify-start text-sm h-9 text-destructive hover:text-destructive" onClick={() => onDelete(session.id)}>
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </Button>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  )
}
