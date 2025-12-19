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
    <div className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-background text-foreground">
      <div className="flex h-20 w-20 items-center justify-center rounded-full bg-destructive/10">
        <AlertTriangle className="h-10 w-10 text-destructive" />
      </div>
      <h2 className="text-2xl font-bold tracking-tight">Something went wrong!</h2>
      <p className="text-muted-foreground max-w-[500px] text-center">
        {error.message || "An unexpected error occurred. Please try refreshing the page."}
      </p>
      <div className="flex gap-4">
        <Button onClick={() => window.location.reload()} variant="outline">
            Refresh Page
        </Button>
        <Button onClick={() => reset()}>
            Try Again
        </Button>
      </div>
    </div>
  )
}
