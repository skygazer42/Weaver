'use client'

import { useEffect, useState } from 'react'
import { fetchPublicConfig, getPublicModels, type PublicConfigModels } from '@/lib/publicConfig'

export interface PublicModelsState {
  isLoading: boolean
  models: PublicConfigModels | null
}

export function usePublicModels(): PublicModelsState {
  const [models, setModels] = useState<PublicConfigModels | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchPublicConfig()
      .then((cfg) => {
        if (cancelled) return
        setModels(getPublicModels(cfg))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { isLoading, models }
}

