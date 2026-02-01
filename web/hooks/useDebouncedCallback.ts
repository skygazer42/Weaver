'use client'

import { useRef, useCallback } from 'react'

/**
 * Custom hook for debounced callbacks
 * Avoids external dependency on use-debounce package
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): (...args: Parameters<T>) => void {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const callbackRef = useRef(callback)

  // Keep callback ref up to date
  callbackRef.current = callback

  return useCallback((...args: Parameters<T>) => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    timeoutRef.current = setTimeout(() => {
      callbackRef.current(...args)
    }, delay)
  }, [delay])
}

/**
 * Hook for throttled callbacks
 * Executes at most once per interval
 */
export function useThrottledCallback<T extends (...args: any[]) => any>(
  callback: T,
  interval: number
): (...args: Parameters<T>) => void {
  const lastRunRef = useRef<number>(0)
  const callbackRef = useRef(callback)

  callbackRef.current = callback

  return useCallback((...args: Parameters<T>) => {
    const now = Date.now()
    if (now - lastRunRef.current >= interval) {
      lastRunRef.current = now
      callbackRef.current(...args)
    }
  }, [interval])
}
