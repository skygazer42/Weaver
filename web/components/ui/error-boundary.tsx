'use client'

import React, { Component, ReactNode } from 'react'
import { AlertCircle, RotateCcw } from 'lucide-react'
import { Button } from './button'
import { cn } from '@/lib/utils'

interface ErrorFallbackProps {
  error: Error
  resetError: () => void
  className?: string
}

/**
 * Functional error fallback component
 */
export function ErrorFallback({ error, resetError, className }: ErrorFallbackProps) {
  return (
    <div
      className={cn(
        "p-4 rounded-lg border border-destructive/50 bg-destructive/10",
        className
      )}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-destructive">Something went wrong</h3>
          <p className="text-sm text-muted-foreground mt-1 break-words">
            {error.message || 'An unexpected error occurred'}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={resetError}
            className="mt-3"
          >
            <RotateCcw className="h-3 w-3 mr-2" />
            Try again
          </Button>
        </div>
      </div>
    </div>
  )
}

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

/**
 * Class-based Error Boundary for catching render errors
 */
export class ChatErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error boundary caught error:', error, errorInfo)
    this.props.onError?.(error, errorInfo)
  }

  resetError = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <ErrorFallback
          error={this.state.error}
          resetError={this.resetError}
        />
      )
    }

    return this.props.children
  }
}

/**
 * Inline error display for non-fatal errors
 */
export function InlineError({
  message,
  onRetry,
  className
}: {
  message: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 text-sm text-destructive",
        className
      )}
      role="alert"
    >
      <AlertCircle className="h-4 w-4 flex-shrink-0" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onRetry}
          className="h-auto py-1 px-2 text-xs"
        >
          <RotateCcw className="h-3 w-3 mr-1" />
          Retry
        </Button>
      )}
    </div>
  )
}
