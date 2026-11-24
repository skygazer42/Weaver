'use client'

import { useCallback, useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  window.addEventListener('storage', onChange)
  return () => window.removeEventListener('storage', onChange)
}

export function useStoredPreference(key: string, defaultValue: string) {
  const value = useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(key) ?? defaultValue,
    () => defaultValue,
  )
  const setValue = useCallback((nextValue: string) => {
    localStorage.setItem(key, nextValue)
    window.dispatchEvent(new StorageEvent('storage', { key, newValue: nextValue }))
  }, [key])
  return [value, setValue] as const
}
