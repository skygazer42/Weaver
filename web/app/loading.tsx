import { LoadingSpinner } from '@/components/ui/loading'

/**
 * Page-level loading state shown by Next.js App Router
 * during route transitions and data fetching.
 */
export default function Loading() {
    return (
        <div className="flex h-dvh w-full items-center justify-center bg-background">
            <div className="flex flex-col items-center gap-6">
                <div className="flex size-16 items-center justify-center rounded-full border border-border/60 bg-card shadow-sm">
                    <LoadingSpinner size="lg" className="text-primary" />
                </div>

                {/* Brand text */}
                <div className="flex flex-col items-center gap-1">
                    <h2 className="text-lg font-semibold text-foreground">Weaver</h2>
                    <p className="text-sm text-muted-foreground">
                        Preparing your workspace…
                    </p>
                </div>
            </div>
        </div>
    )
}
