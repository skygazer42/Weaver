'use client'

import React from 'react'
import { ArrowDown, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ArtifactsPanel } from './ArtifactsPanel'
import { Artifact, PendingInterrupt } from '@/types/chat'

interface ScrollButtonProps {
  visible: boolean
  onClick: () => void
}

export function ScrollToBottomButton({ visible, onClick }: ScrollButtonProps) {
  return (
    <div className={cn(
      "absolute bottom-24 right-6 z-30 transition-all duration-500",
      visible
        ? "translate-y-0 opacity-100"
        : "translate-y-10 opacity-0 pointer-events-none"
    )}>
      <Button
        variant="outline"
        size="icon"
        className="rounded-full shadow-lg bg-background/80 backdrop-blur border-primary/20 hover:bg-background"
        onClick={onClick}
        aria-label="Scroll to bottom"
      >
        <ArrowDown className="h-4 w-4" />
      </Button>
    </div>
  )
}

interface InterruptBannerProps {
  pendingInterrupt: PendingInterrupt | null
  isLoading: boolean
  onApprove: () => void
  onDismiss: () => void
}

export function InterruptBanner({ pendingInterrupt, isLoading, onApprove, onDismiss }: InterruptBannerProps) {
  if (!pendingInterrupt) return null

  return (
    <div
      className="mx-4 mb-3 p-3 border rounded-xl bg-amber-50 text-amber-900 shadow-sm flex flex-col gap-2"
      role="alert"
    >
      <div className="text-sm font-semibold">Tool approval required</div>
      <div className="text-xs text-amber-800">
        {pendingInterrupt.message || pendingInterrupt?.prompts?.[0]?.message || 'Approve tool execution to continue.'}
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={onApprove} disabled={isLoading}>
          Approve & Continue
        </Button>
        <Button size="sm" variant="ghost" onClick={onDismiss} disabled={isLoading}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}

interface MobileArtifactsOverlayProps {
  show: boolean
  artifacts: Artifact[]
  onClose: () => void
}

export function MobileArtifactsOverlay({ show, artifacts, onClose }: MobileArtifactsOverlayProps) {
  if (!show) return null

  return (
    <div className="fixed inset-0 z-50 bg-background xl:hidden flex flex-col animate-in slide-in-from-right duration-300">
      <div className="flex items-center justify-between p-4 border-b">
        <h2 className="font-semibold">Artifacts</h2>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close artifacts">
          <X className="h-5 w-5" />
        </Button>
      </div>
      <div className="flex-1 overflow-hidden">
        <ArtifactsPanel artifacts={artifacts} />
      </div>
    </div>
  )
}
