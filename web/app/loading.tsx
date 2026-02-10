import { LoadingSpinner } from '@/components/ui/loading'

/**
 * Page-level loading state shown by Next.js App Router
 * during route transitions and data fetching.
 */
export default function Loading() {
    return (
        <div className="flex h-dvh w-full items-center justify-center bg-background">
            <div className="flex flex-col items-center gap-6">
                {/* Animated gradient ring */}
                <div className="relative">
                    <div className="absolute inset-0 rounded-full gradient-accent opacity-20 blur-xl animate-pulse-glow" />
                    <div className="relative flex h-16 w-16 items-center justify-center rounded-full glass">
                        <LoadingSpinner size="lg" className="text-primary" />
                    </div>
                </div>

                {/* Brand text */}
                <div className="flex flex-col items-center gap-1">
                    <h2 className="text-lg font-semibold gradient-text">Weaver</h2>
                    <p className="text-sm text-muted-foreground animate-pulse">
                        Preparing your workspace…
                    </p>
                </div>
            </div>
        </div>
    )
}
