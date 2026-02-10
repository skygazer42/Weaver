'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { Home, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Custom 404 Not Found page with animated visuals matching the Weaver design system.
 */
export default function NotFound() {
    return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
            {/* Animated 404 glyph */}
            <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
                className="relative mb-8"
            >
                <span className="text-[10rem] font-extrabold leading-none tracking-tighter gradient-text select-none">
                    404
                </span>
                {/* Glow halo behind the number */}
                <div className="absolute inset-0 -z-10 blur-3xl opacity-30 gradient-primary rounded-full" />
            </motion.div>

            {/* Copy */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.5 }}
                className="flex flex-col items-center gap-3 text-center"
            >
                <h1 className="text-2xl font-bold tracking-tight text-foreground">
                    Page Not Found
                </h1>
                <p className="max-w-md text-muted-foreground">
                    The page you&apos;re looking for doesn&apos;t exist or has been moved.
                    Let&apos;s get you back on track.
                </p>
            </motion.div>

            {/* Actions */}
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5, duration: 0.4 }}
                className="mt-8 flex gap-4"
            >
                <Button asChild variant="outline" className="gap-2">
                    <Link href="/">
                        <Home className="h-4 w-4" />
                        Back to Home
                    </Link>
                </Button>
                <Button asChild className="gap-2 gradient-accent text-white border-0 hover:opacity-90">
                    <Link href="/">
                        <Search className="h-4 w-4" />
                        Start Researching
                    </Link>
                </Button>
            </motion.div>
        </div>
    )
}
