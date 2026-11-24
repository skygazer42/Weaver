'use client'

import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { AlertTriangle } from 'lucide-react'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-surface-subtle/50 p-4 text-foreground sm:p-6">
      <div className="w-full max-w-lg space-y-5 rounded-lg border border-border/80 bg-card p-6 shadow-surface sm:p-8">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-destructive-border bg-destructive-surface">
            <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden="true" />
          </div>
          <h2 className="text-xl font-semibold tracking-tight">Something went wrong!</h2>
        </div>
        <p role="alert" className="break-words rounded-lg border border-destructive-border bg-destructive-surface p-3 text-sm leading-relaxed text-destructive">
          {error.message || "An unexpected error occurred. Please try refreshing the page."}
        </p>
        <div className="flex flex-wrap justify-end gap-2 border-t border-border/70 pt-4">
          <Button onClick={() => window.location.reload()} variant="outline">
            Refresh Page
          </Button>
          <Button onClick={() => reset()}>
            Try Again
          </Button>
        </div>
      </div>
    </div>
  )
}
