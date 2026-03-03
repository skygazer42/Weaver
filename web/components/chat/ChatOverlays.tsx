'use client'

import { useEffect, useMemo, useState } from 'react'
import { ArrowDown } from '@/components/ui/icons'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { isHitlToolApprovalRequest } from '@/lib/hitl'
import { ArtifactsPanel } from './ArtifactsPanel'
import { Artifact, PendingInterrupt } from '@/types/chat'

interface ScrollButtonProps {
  visible: boolean
  onClick: () => void
}

export function ScrollToBottomButton({ visible, onClick }: ScrollButtonProps) {
  return (
    <div className={cn(
      "absolute right-6 z-30 transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
      visible
        ? "translate-y-0 opacity-100"
        : "translate-y-8 opacity-0 pointer-events-none"
    )}
    style={{ bottom: 'calc(6rem + env(safe-area-inset-bottom, 0px))' }}
    >
      <Button
        variant="outline"
        size="icon"
        className="rounded-full bg-card/80 backdrop-blur-xl border-border/30 shadow-lg hover:bg-card hover:shadow-xl transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] h-9 w-9"
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
  onReject?: (message?: string) => void
  onEdit?: (editedArgs: Array<Record<string, unknown> | undefined>) => void
  onDismiss: () => void
}

export function InterruptBanner({
  pendingInterrupt,
  isLoading,
  onApprove,
  onReject,
  onEdit,
  onDismiss,
}: InterruptBannerProps) {
  const prompt = pendingInterrupt?.prompts?.[0]
  const toolApprovalRequest = useMemo(() => {
    if (isHitlToolApprovalRequest(prompt)) return prompt
    return null
  }, [prompt])

  const [editMode, setEditMode] = useState(false)
  const [argsDrafts, setArgsDrafts] = useState<string[]>([])
  const [parseErrors, setParseErrors] = useState<Array<string | null>>([])

  useEffect(() => {
    if (!toolApprovalRequest) {
      setEditMode(false)
      setArgsDrafts([])
      setParseErrors([])
      return
    }

    const drafts = (toolApprovalRequest.action_requests || []).map((req) => {
      try {
        return JSON.stringify(req.args || {}, null, 2)
      } catch {
        return '{}'
      }
    })
    setEditMode(false)
    setArgsDrafts(drafts)
    setParseErrors(drafts.map(() => null))
  }, [toolApprovalRequest])

  const bannerMessage = useMemo(() => {
    if (!pendingInterrupt) return 'Approval required before continuing.'
    if (pendingInterrupt.message) return pendingInterrupt.message
    if (prompt && typeof prompt === 'object' && !Array.isArray(prompt)) {
      const record = prompt as Record<string, unknown>
      if (typeof record.message === 'string' && record.message.trim()) return record.message.trim()
    }
    if (toolApprovalRequest) {
      const count = toolApprovalRequest.action_requests?.length || 0
      if (count === 1) return 'Approve to run 1 tool call.'
      if (count > 1) return `Approve to run ${count} tool calls.`
      return 'Approve tool execution to continue.'
    }
    return 'Approval required before continuing.'
  }, [pendingInterrupt, prompt, toolApprovalRequest])

  const handleContinue = () => {
    if (!pendingInterrupt) return
    if (!toolApprovalRequest) {
      onApprove()
      return
    }

    if (!editMode) {
      onApprove()
      return
    }

    if (!onEdit) return

    const nextErrors: Array<string | null> = argsDrafts.map(() => null)
    const parsedArgs: Array<Record<string, unknown> | undefined> = []

    for (let i = 0; i < argsDrafts.length; i++) {
      const raw = (argsDrafts[i] || '').trim()
      try {
        const parsed = raw ? (JSON.parse(raw) as unknown) : {}
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          nextErrors[i] = 'Args must be a JSON object.'
          parsedArgs.push(undefined)
          continue
        }
        parsedArgs.push(parsed as Record<string, unknown>)
      } catch (e) {
        nextErrors[i] = e instanceof Error ? e.message : 'Invalid JSON.'
        parsedArgs.push(undefined)
      }
    }

    if (nextErrors.some(Boolean)) {
      setParseErrors(nextErrors)
      return
    }

    onEdit(parsedArgs)
  }

  if (!pendingInterrupt) return null

  return (
    <div
      className={cn(
        "mx-4 mb-3 p-3.5 rounded-xl border shadow-sm flex flex-col gap-2 transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
        "bg-amber-50/40 text-amber-950 border-border/30",
        "dark:bg-amber-950/10 dark:text-amber-50 dark:border-border/30"
      )}
      role="alert"
    >
      <div className="text-[13px] font-medium">Tool approval required</div>
      <div className="text-xs text-amber-900/60 dark:text-amber-100/60 text-pretty">
        {bannerMessage}
      </div>

      {toolApprovalRequest ? (
        <div className="mt-1 flex flex-col gap-2">
          {(toolApprovalRequest.action_requests || []).map((req, idx) => {
            const argsPreview =
              typeof req.args === 'object' && req.args && !Array.isArray(req.args)
                ? JSON.stringify(req.args, null, 2)
                : '{}'

            return (
              <div
                key={`${req.name}-${idx}`}
                className={cn(
                  'rounded-lg border border-border/40 bg-background/60 dark:bg-background/20',
                  'p-2.5',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-medium">{req.name}</div>
                  <div className="text-[11px] text-amber-900/50 dark:text-amber-100/50">tool</div>
                </div>

                {!editMode ? (
                  <pre className="mt-1.5 text-[11px] leading-4 whitespace-pre-wrap break-words text-amber-950/70 dark:text-amber-50/70 max-h-40 overflow-auto">
                    {argsPreview}
                  </pre>
                ) : (
                  <div className="mt-1.5">
                    <Textarea
                      value={argsDrafts[idx] || ''}
                      onChange={(e) => {
                        const next = argsDrafts.slice()
                        next[idx] = e.target.value
                        setArgsDrafts(next)
                        if (parseErrors[idx]) {
                          const nextErrors = parseErrors.slice()
                          nextErrors[idx] = null
                          setParseErrors(nextErrors)
                        }
                      }}
                      className="font-mono text-[11px] leading-4 min-h-[110px]"
                      spellCheck={false}
                    />
                    {parseErrors[idx] ? (
                      <div className="mt-1 text-[11px] text-red-700 dark:text-red-300">
                        {parseErrors[idx]}
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            )
          })}

          <div className="flex items-center justify-between gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="h-8 text-xs"
              onClick={() => setEditMode((v) => !v)}
              disabled={isLoading || !onEdit}
            >
              {editMode ? 'Stop editing' : 'Edit args'}
            </Button>

            {editMode ? (
              <div className="text-[11px] text-amber-900/50 dark:text-amber-100/50">
                JSON object only
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="flex gap-2 mt-0.5">
        <Button size="sm" className="h-8 text-xs" onClick={handleContinue} disabled={isLoading}>
          Approve & Continue
        </Button>
        {toolApprovalRequest && onReject ? (
          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs"
            onClick={() => onReject()}
            disabled={isLoading}
          >
            Reject
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={onDismiss} disabled={isLoading}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}

interface MobileArtifactsOverlayProps {
  show: boolean
  artifacts: Artifact[]
  threadId: string | null
  onClose: () => void
}

export function MobileArtifactsOverlay({ show, artifacts, threadId, onClose }: MobileArtifactsOverlayProps) {
  if (!show) return null

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-xl xl:hidden flex flex-col transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]">
      <ArtifactsPanel
        artifacts={artifacts}
        threadId={threadId}
        isOpen={true}
        onToggle={onClose}
        toggleLabel="Close inspector"
        toggleTitle="Close inspector"
        allowFullscreen={false}
      />
    </div>
  )
}
