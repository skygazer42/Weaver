'use client'

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { MessageSquare, Send, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { getApiBaseUrl } from '@/lib/api'

interface Comment {
  id: string
  thread_id: string
  message_id: string | null
  author: string
  content: string
  created_at: string
}

interface CommentsPanelProps {
  threadId: string
  isOpen: boolean
  onClose: () => void
  className?: string
}

export function CommentsPanel({ threadId, isOpen, onClose, className }: CommentsPanelProps) {
  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [authorName, setAuthorName] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const fetchComments = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/sessions/${threadId}/comments`)
      const data = await response.json()
      setComments(data.comments || [])
    } catch {
      toast.error('Failed to load comments')
    }
  }, [threadId])

  useEffect(() => {
    if (isOpen && threadId) {
      fetchComments()
    }
  }, [isOpen, threadId, fetchComments])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [comments])

  const submitComment = async () => {
    if (!newComment.trim()) return

    setIsSubmitting(true)
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/sessions/${threadId}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: newComment.trim(),
          author: authorName.trim() || 'anonymous',
        }),
      })
      const data = await response.json()
      if (data.success) {
        setComments(prev => [...prev, data.comment])
        setNewComment('')
      }
    } catch {
      toast.error('Failed to add comment')
    } finally {
      setIsSubmitting(false)
    }
  }

  const formatTime = (iso: string) => {
    const date = new Date(iso)
    return date.toLocaleString()
  }

  if (!isOpen) return null

  return (
    <div className={cn(
      "fixed right-0 top-0 h-full w-80 z-50 flex flex-col",
      "glass-strong border-l shadow-2xl",
      "animate-slide-in-right",
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-blue-500" />
          <h3 className="font-semibold">Comments</h3>
          <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">
            {comments.length}
          </span>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Comments List */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {comments.length === 0 ? (
          <div className="text-center text-muted-foreground text-sm py-8">
            No comments yet. Be the first to comment!
          </div>
        ) : (
          comments.map(comment => (
            <div
              key={comment.id}
              className="p-3 rounded-xl bg-muted/30 border border-muted/50 space-y-1 animate-fade-in"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-foreground">
                  {comment.author}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatTime(comment.created_at)}
                </span>
              </div>
              <p className="text-sm text-foreground/90">{comment.content}</p>
            </div>
          ))
        )}
      </div>

      {/* Input Area */}
      <div className="p-4 border-t space-y-2">
        {!authorName && (
          <input
            type="text"
            placeholder="Your name (optional)"
            value={authorName}
            onChange={(e) => setAuthorName(e.target.value)}
            className="w-full px-3 py-1.5 text-xs rounded-lg bg-muted/50 border border-muted focus:outline-none focus:ring-1 focus:ring-blue-500/50"
          />
        )}
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Write a comment..."
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitComment()}
            className="flex-1 px-3 py-2 text-sm rounded-xl bg-muted/50 border border-muted focus:outline-none focus:ring-1 focus:ring-blue-500/50"
          />
          <Button
            variant="gradient"
            size="icon"
            onClick={submitComment}
            disabled={!newComment.trim() || isSubmitting}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
