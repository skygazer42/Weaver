'use client'

import React, { useState, useRef } from 'react'
import { cn } from '@/lib/utils'
import { Copy, Check, Link, X, Clock, Eye, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { getApiBaseUrl } from '@/lib/api'
import { useFocusTrap } from '@/hooks/useFocusTrap'

interface ShareDialogProps {
  threadId: string
  isOpen: boolean
  onClose: () => void
  className?: string
}

interface ShareLink {
  id: string
  permissions: string
  created_at: string
  expires_at: string | null
  view_count: number
}

export function ShareDialog({ threadId, isOpen, onClose, className }: ShareDialogProps) {
  const [shareLinks, setShareLinks] = useState<ShareLink[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const [permissions, setPermissions] = useState<'view' | 'comment'>('view')
  const [expiresHours, setExpiresHours] = useState(72)
  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef, isOpen, onClose)

  const createShareLink = async () => {
    setIsCreating(true)
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/sessions/${threadId}/share`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          permissions,
          expires_hours: expiresHours,
        }),
      })
      const data = await response.json()
      if (data.success) {
        setShareLinks(prev => [data.share, ...prev])
        toast.success('Share link created')
      }
    } catch (error) {
      toast.error('Failed to create share link')
    } finally {
      setIsCreating(false)
    }
  }

  const copyLink = (shareId: string) => {
    const url = `${window.location.origin}/share/${shareId}`
    navigator.clipboard.writeText(url)
    setCopied(shareId)
    toast.success('Link copied')
    setTimeout(() => setCopied(null), 2000)
  }

  const deleteLink = async (shareId: string) => {
    try {
      await fetch(`${getApiBaseUrl()}/api/share/${shareId}`, { method: 'DELETE' })
      setShareLinks(prev => prev.filter(l => l.id !== shareId))
      toast.success('Share link deleted')
    } catch {
      toast.error('Failed to delete share link')
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-dialog-title"
        className={cn(
          "w-full max-w-md mx-4 rounded-2xl glass-strong p-6 shadow-2xl animate-scale-in",
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg gradient-accent">
              <Link className="h-5 w-5 text-white" />
            </div>
            <div>
              <h3 id="share-dialog-title" className="font-semibold text-lg">Share Research</h3>
              <p className="text-xs text-muted-foreground">Create a link to share this session</p>
            </div>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Options */}
        <div className="space-y-4 mb-6">
          <div className="flex gap-2">
            <button
              onClick={() => setPermissions('view')}
              className={cn(
                "flex-1 flex items-center gap-2 p-3 rounded-xl border transition-all",
                permissions === 'view'
                  ? "border-blue-500/50 bg-blue-500/10"
                  : "border-muted hover:border-muted-foreground/30"
              )}
            >
              <Eye className="h-4 w-4" />
              <span className="text-sm font-medium">View Only</span>
            </button>
            <button
              onClick={() => setPermissions('comment')}
              className={cn(
                "flex-1 flex items-center gap-2 p-3 rounded-xl border transition-all",
                permissions === 'comment'
                  ? "border-purple-500/50 bg-purple-500/10"
                  : "border-muted hover:border-muted-foreground/30"
              )}
            >
              <Lock className="h-4 w-4" />
              <span className="text-sm font-medium">Comment</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Expires in:</span>
            <select
              value={expiresHours}
              onChange={(e) => setExpiresHours(Number(e.target.value))}
              className="bg-muted/50 border border-muted rounded-lg px-2 py-1 text-sm"
            >
              <option value={24}>24 hours</option>
              <option value={72}>3 days</option>
              <option value={168}>7 days</option>
              <option value={720}>30 days</option>
            </select>
          </div>
        </div>

        {/* Create Button */}
        <Button
          variant="gradient"
          className="w-full mb-6"
          onClick={createShareLink}
          loading={isCreating}
        >
          Create Share Link
        </Button>

        {/* Existing Links */}
        {shareLinks.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Active Links
            </h4>
            {shareLinks.map(link => (
              <div
                key={link.id}
                className="flex items-center gap-2 p-2 rounded-lg bg-muted/30 border border-muted/50"
              >
                <Link className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                <span className="text-xs text-muted-foreground truncate flex-1">
                  /share/{link.id}
                </span>
                <span className="text-xs text-muted-foreground/50 flex-shrink-0">
                  {link.view_count} views
                </span>
                <button
                  onClick={() => copyLink(link.id)}
                  className="p-1 hover:bg-muted/50 rounded transition-colors"
                >
                  {copied === link.id ? (
                    <Check className="h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                </button>
                <button
                  onClick={() => deleteLink(link.id)}
                  className="p-1 hover:bg-destructive/10 rounded transition-colors"
                >
                  <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
