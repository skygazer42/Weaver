'use client'

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
      "absolute right-6 z-30 transition duration-200 ease-out",
      visible
        ? "translate-y-0 opacity-100"
        : "translate-y-10 opacity-0 pointer-events-none"
    )}
    style={{ bottom: 'calc(6rem + env(safe-area-inset-bottom, 0px))' }}
    >
      <Button
        variant="outline"
        size="icon"
        className="rounded-full bg-background border border-border/60 shadow-md hover:bg-accent"
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
      className={cn(
        "mx-4 mb-3 p-3 rounded-xl border shadow-sm flex flex-col gap-2",
        "bg-amber-50/80 text-amber-950 border-amber-200/70",
        "dark:bg-amber-950/30 dark:text-amber-50 dark:border-amber-900/40"
      )}
      role="alert"
    >
      <div className="text-sm font-semibold text-balance">Tool approval required</div>
      <div className="text-xs text-amber-900/80 dark:text-amber-100/80 text-pretty">
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
    <div className="fixed inset-0 z-50 bg-background xl:hidden flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-border/60">
        <h2 className="font-semibold">Artifacts</h2>
        <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close artifacts">
          <X className="h-5 w-5" />
        </Button>
      </div>
      <div className="flex-1 overflow-hidden">
        <ArtifactsPanel artifacts={artifacts} />
      </div>
    </div>
  )
}
