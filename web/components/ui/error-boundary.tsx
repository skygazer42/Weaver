'use client'

import React, { Component, ReactNode, useState as useStateImport } from 'react'
import { AlertCircle, RotateCcw, Copy, Check } from 'lucide-react'
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
  const [copied, setCopied] = useStateImport(false)

  const handleCopyError = async () => {
    const details = [
      `Error: ${error.message}`,
      `Timestamp: ${new Date().toISOString()}`,
      `Stack: ${error.stack || 'N/A'}`,
      `URL: ${typeof window !== 'undefined' ? window.location.href : 'N/A'}`,
    ].join('\n')
    try {
      await navigator.clipboard.writeText(details)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback: select text
      console.warn('Clipboard API not available')
    }
  }

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
          <div className="flex items-center gap-2 mt-3">
            <Button
              variant="outline"
              size="sm"
              onClick={resetError}
            >
              <RotateCcw className="h-3 w-3 mr-2" />
              Try again
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopyError}
            >
              {copied ? (
                <><Check className="h-3 w-3 mr-2" /> Copied</>
              ) : (
                <><Copy className="h-3 w-3 mr-2" /> Copy error details</>
              )}
            </Button>
          </div>
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
    console.error('[ErrorBoundary] Render crash:', {
      component: this.constructor.name,
      error: error.message,
      stack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
    })
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
