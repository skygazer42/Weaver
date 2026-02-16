'use client'

import Link from 'next/link'
import { Home, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Custom 404 Not Found page with animated visuals matching the Weaver design system.
 */
export default function NotFound() {
    return (
        <div className="flex min-h-dvh flex-col items-center justify-center bg-background px-4">
            <div className="relative mb-8">
                <span className="text-[10rem] font-extrabold leading-none text-foreground/10 select-none tabular-nums">
                    404
                </span>
            </div>

            {/* Copy */}
            <div className="flex flex-col items-center gap-3 text-center">
                <h1 className="text-2xl font-bold text-foreground">
                    Page Not Found
                </h1>
                <p className="max-w-md text-muted-foreground">
                    The page you&apos;re looking for doesn&apos;t exist or has been moved.
                    Let&apos;s get you back on track.
                </p>
            </div>

            {/* Actions */}
            <div className="mt-8 flex gap-4">
                <Button asChild variant="outline" className="gap-2">
                    <Link href="/">
                        <Home className="h-4 w-4" />
                        Back to Home
                    </Link>
                </Button>
                <Button asChild className="gap-2">
                    <Link href="/">
                        <Search className="h-4 w-4" />
                        Start Researching
                    </Link>
                </Button>
            </div>
        </div>
    )
}
