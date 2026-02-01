/**
 * Structured error handling utilities
 */

export type ErrorCode = 'NETWORK' | 'TIMEOUT' | 'SERVER' | 'INVALID_INPUT' | 'UNKNOWN'

export interface AppError {
  code: ErrorCode
  message: string
  retryable: boolean
  details?: string
}

/**
 * Create a structured AppError from any error type
 */
export function createAppError(error: unknown): AppError {
  // Handle AbortError (request cancelled)
  if (error instanceof Error) {
    if (error.name === 'AbortError') {
      return {
        code: 'TIMEOUT',
        message: 'Request was cancelled',
        retryable: false
      }
    }

    // Handle network errors
    if (error.message.includes('fetch') || error.message.includes('network')) {
      return {
        code: 'NETWORK',
        message: 'Network error. Please check your connection.',
        retryable: true
      }
    }

    // Handle timeout
    if (error.message.includes('timeout')) {
      return {
        code: 'TIMEOUT',
        message: 'Request timed out. Please try again.',
        retryable: true
      }
    }

    // Handle server errors
    if (error.message.includes('500') || error.message.includes('server')) {
      return {
        code: 'SERVER',
        message: 'Server error. Please try again later.',
        retryable: true
      }
    }

    // Generic error with message
    return {
      code: 'UNKNOWN',
      message: error.message || 'An unexpected error occurred',
      retryable: false,
      details: error.stack
    }
  }

  // Handle non-Error objects
  if (typeof error === 'string') {
    return {
      code: 'UNKNOWN',
      message: error,
      retryable: false
    }
  }

  // Fallback
  return {
    code: 'UNKNOWN',
    message: 'An unexpected error occurred',
    retryable: false,
    details: String(error)
  }
}

/**
 * Get user-friendly error message
 */
export function getErrorMessage(error: AppError): string {
  switch (error.code) {
    case 'NETWORK':
      return 'Unable to connect. Please check your internet connection and try again.'
    case 'TIMEOUT':
      return 'The request took too long. Please try again.'
    case 'SERVER':
      return 'Something went wrong on our end. Please try again later.'
    case 'INVALID_INPUT':
      return error.message || 'Invalid input. Please check your data and try again.'
    default:
      return error.message || 'An unexpected error occurred. Please try again.'
  }
}

/**
 * Check if error is likely transient and can be retried
 */
export function isRetryableError(error: AppError): boolean {
  return error.retryable
}
