'use client'

import React, { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { History, Clock, RotateCcw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { getApiBaseUrl } from '@/lib/api'

interface Version {
  id: string
  thread_id: string
  version_number: number
  label: string
  created_at: string
  snapshot_size: number
}

interface VersionHistoryProps {
  threadId: string
  isOpen: boolean
  onClose: () => void
  onRestore?: (snapshot: any) => void
  className?: string
}

export function VersionHistory({ threadId, isOpen, onClose, onRestore, className }: VersionHistoryProps) {
  const [versions, setVersions] = useState<Version[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [restoringId, setRestoringId] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen && threadId) {
      fetchVersions()
    }
  }, [isOpen, threadId])

  const fetchVersions = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/sessions/${threadId}/versions`)
      const data = await response.json()
      setVersions(data.versions || [])
    } catch {
      toast.error('Failed to load version history')
    } finally {
      setIsLoading(false)
    }
  }

  const createVersion = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/sessions/${threadId}/versions`, {
        method: 'POST',
      })
      const data = await response.json()
      if (data.success) {
        setVersions(prev => [...prev, data.version])
        toast.success('Version saved')
      }
    } catch {
      toast.error('Failed to create version')
    }
  }

  const restoreVersion = async (versionId: string) => {
    setRestoringId(versionId)
    try {
      const response = await fetch(
        `${getApiBaseUrl()}/api/sessions/${threadId}/restore/${versionId}`,
        { method: 'POST' }
      )
      const data = await response.json()
      if (data.success && onRestore) {
        onRestore(data.snapshot)
        toast.success('Version restored')
        onClose()
      }
    } catch {
      toast.error('Failed to restore version')
    } finally {
      setRestoringId(null)
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
  }

  const formatTime = (iso: string) => {
    const date = new Date(iso)
    return date.toLocaleString()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className={cn(
        "w-full max-w-lg mx-4 rounded-2xl glass-strong p-6 shadow-2xl animate-scale-in max-h-[80vh] flex flex-col",
        className
      )}>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-gradient-to-r from-green-500/20 to-emerald-500/20">
              <History className="h-5 w-5 text-green-500" />
            </div>
            <div>
              <h3 className="font-semibold text-lg">Version History</h3>
              <p className="text-xs text-muted-foreground">{versions.length} versions saved</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="soft" size="sm" onClick={createVersion}>
              Save Current
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Versions List */}
        <div className="flex-1 overflow-y-auto space-y-2">
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-16 rounded-xl bg-muted/30 animate-pulse" />
              ))}
            </div>
          ) : versions.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-12">
              <History className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p>No versions saved yet</p>
              <p className="text-xs mt-1">Click &quot;Save Current&quot; to create a snapshot</p>
            </div>
          ) : (
            versions.slice().reverse().map((version) => (
              <div
                key={version.id}
                className="p-4 rounded-xl border bg-gradient-to-r from-muted/20 to-transparent hover:from-muted/40 transition-all group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{version.label}</span>
                      <span className="text-xs text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                        v{version.version_number}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatTime(version.created_at)}
                      </span>
                      <span>{formatSize(version.snapshot_size)}</span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => restoreVersion(version.id)}
                    loading={restoringId === version.id}
                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <RotateCcw className="h-4 w-4 mr-1" />
                    Restore
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
