'use client'

import React from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = {
  sm: 'h-3 w-3',
  md: 'h-4 w-4',
  lg: 'h-6 w-6'
}

export function LoadingSpinner({ size = 'md', className }: LoadingSpinnerProps) {
  return (
    <Loader2
      className={cn('animate-spin', sizes[size], className)}
      aria-hidden="true"
    />
  )
}

interface LoadingSkeletonProps {
  className?: string
}

export function LoadingSkeleton({ className }: LoadingSkeletonProps) {
  return (
    <div
      className={cn('animate-pulse bg-muted rounded', className)}
      aria-hidden="true"
    />
  )
}

export function LoadingDots({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex gap-1", className)} aria-hidden="true">
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="h-1.5 w-1.5 bg-current rounded-full animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </span>
  )
}

// Full-page loading indicator
export function LoadingPage() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <LoadingSpinner size="lg" className="text-primary" />
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    </div>
  )
}

// Inline loading indicator with text
export function LoadingInline({ text = 'Loading...' }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <LoadingSpinner size="sm" />
      <span>{text}</span>
    </div>
  )
}
