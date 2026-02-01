'use client'

import React, { useRef, useCallback, memo } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { MessageItem } from './MessageItem'
import { Loader2 } from 'lucide-react'
import { Message } from '@/types/chat'

interface ChatMessagesProps {
  messages: Message[]
  isLoading: boolean
  currentStatus: string
  onEditMessage: (id: string, newContent: string) => void
  onAtBottomChange?: (atBottom: boolean) => void
}

// Memoized message wrapper to prevent unnecessary re-renders
const MessageWrapper = memo(function MessageWrapper({
  message,
  onEdit
}: {
  message: Message
  onEdit: (id: string, newContent: string) => void
}) {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-0">
      <MessageItem message={message} onEdit={onEdit} />
    </div>
  )
})

export function ChatMessages({
  messages,
  isLoading,
  currentStatus,
  onEditMessage,
  onAtBottomChange
}: ChatMessagesProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const lastAtBottom = useRef<boolean | null>(null)

  // Memoized renderer for Virtuoso
  const itemContent = useCallback((index: number, message: Message) => (
    <MessageWrapper key={message.id} message={message} onEdit={onEditMessage} />
  ), [onEditMessage])

  // Handle scroll position changes
  const handleAtBottomChange = useCallback((atBottom: boolean) => {
    if (lastAtBottom.current === atBottom) return
    lastAtBottom.current = atBottom
    onAtBottomChange?.(atBottom)
  }, [onAtBottomChange])

  // Scroll to bottom method exposed via ref
  const scrollToBottom = useCallback(() => {
    const idx = messages.length - 1
    if (idx >= 0) {
      virtuosoRef.current?.scrollToIndex({
        index: idx,
        align: 'end',
        behavior: 'smooth'
      })
    }
  }, [messages.length])

  // Footer component showing loading status
  const Footer = useCallback(() => (
    <div className="max-w-5xl mx-auto px-4 sm:px-0 pb-4">
      {currentStatus && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-2 animate-in fade-in slide-in-from-bottom-2">
          {isLoading && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
          <span className="font-medium animate-pulse">{currentStatus}</span>
        </div>
      )}
      <div className="h-4" />
    </div>
  ), [currentStatus, isLoading])

  return (
    <Virtuoso
      ref={virtuosoRef}
      data={messages}
      followOutput="auto"
      atBottomStateChange={handleAtBottomChange}
      className="scrollbar-thin scrollbar-thumb-muted/20"
      itemContent={itemContent}
      components={{ Footer }}
    />
  )
}

// Export ref methods type for parent component
export type ChatMessagesHandle = {
  scrollToBottom: () => void
}
