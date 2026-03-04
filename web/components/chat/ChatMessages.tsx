'use client'

import { useRef, useCallback, memo } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { MessageItem } from './MessageItem'
import { AlertTriangle, Code, Loader2, Search, ListChecks, PenLine, WifiOff } from '@/components/ui/icons'
import { Message } from '@/types/chat'
import { cn } from '@/lib/utils'

interface ChatMessagesProps {
  messages: Message[]
  isLoading: boolean
  currentStatus: string
  connectionState?: 'connected' | 'reconnecting' | 'disconnected'
  onEditMessage: (id: string, newContent: string) => void
  onAtBottomChange?: (atBottom: boolean) => void
}

const MessageWrapper = memo(function MessageWrapper({
  message,
  onEdit
}: {
  message: Message
  onEdit: (id: string, newContent: string) => void
}) {
  return (
    <div className="max-w-[820px] mx-auto px-4 animate-message-in">
      <MessageItem message={message} onEdit={onEdit} />
    </div>
  )
})

export function ChatMessages({
  messages,
  isLoading,
  currentStatus,
  connectionState = 'connected',
  onEditMessage,
  onAtBottomChange
}: ChatMessagesProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const lastAtBottom = useRef<boolean | null>(null)

  const itemContent = useCallback((index: number, message: Message) => (
    <MessageWrapper key={`${message.id}-${index}`} message={message} onEdit={onEditMessage} />
  ), [onEditMessage])

  const handleAtBottomChange = useCallback((atBottom: boolean) => {
    if (lastAtBottom.current === atBottom) return
    lastAtBottom.current = atBottom
    onAtBottomChange?.(atBottom)
  }, [onAtBottomChange])

  const Footer = useCallback(() => (
    <div className="max-w-[820px] mx-auto px-4 pb-4">
      {currentStatus && (
        <StreamStatus
          text={currentStatus}
          isLoading={isLoading}
          connectionState={connectionState}
        />
      )}
      <div className="h-4" />
    </div>
  ), [currentStatus, isLoading, connectionState])

  return (
    <Virtuoso
      ref={virtuosoRef}
      data={messages}
      followOutput="auto"
      atBottomStateChange={handleAtBottomChange}
      className="scrollbar-thin scrollbar-thumb-muted/20"
      itemContent={itemContent}
      components={{ Footer }}
      overscan={{ main: 400, reverse: 400 }}
      increaseViewportBy={200}
    />
  )
}

export type ChatMessagesHandle = {
  scrollToBottom: () => void
}

function StreamStatus({
  text,
  isLoading,
  connectionState,
}: {
  text: string
  isLoading: boolean
  connectionState: 'connected' | 'reconnecting' | 'disconnected'
}) {
  const raw = String(text || '').trim()
  if (!raw) return null

  const lower = raw.toLowerCase()

  const Icon = (() => {
    if (connectionState === 'disconnected') return WifiOff
    if (connectionState === 'reconnecting' || lower.includes('reconnect')) return AlertTriangle
    if (lower.includes('plan') || lower.includes('planner')) return ListChecks
    if (lower.includes('search') || lower.includes('query')) return Search
    if (lower.includes('write') || lower.includes('synthes') || lower.includes('report')) return PenLine
    if (lower.includes('tool') || lower.includes('execute') || lower.includes('python') || lower.includes('code')) return Code
    return Loader2
  })()

  const isError = connectionState === 'disconnected'
  const isWarning = connectionState === 'reconnecting'

  const iconColor = (() => {
    if (isError) return 'text-destructive'
    if (isWarning) return 'text-amber-500'
    if (Icon === Search) return 'text-emerald-500 dark:text-emerald-400'
    if (Icon === Code) return 'text-sky-500 dark:text-sky-400'
    if (Icon === PenLine) return 'text-violet-500 dark:text-violet-400'
    if (Icon === ListChecks) return 'text-primary'
    return 'text-muted-foreground'
  })()

  return (
    <div className="py-3 animate-fade-in">
      <div
        className="flex items-center gap-2.5"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <span className={cn(
          "size-1.5 rounded-full shrink-0",
          isError
            ? "bg-destructive"
            : isWarning
              ? "bg-amber-500"
              : isLoading
                ? "bg-primary animate-pulse"
                : "bg-muted-foreground/40"
        )} />

        {isLoading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />
        ) : (
          <Icon className={cn(
            "h-3.5 w-3.5 shrink-0",
            iconColor
          )} />
        )}

        <span className={cn(
          "text-[13px] font-medium truncate",
          isError
            ? "text-destructive font-semibold"
            : "text-muted-foreground"
        )}>
          {raw}
        </span>
      </div>
    </div>
  )
}
