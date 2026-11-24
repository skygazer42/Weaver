'use client'

import { useEffect, useState } from 'react'
import { DEFAULT_MODEL } from '@/lib/constants'
import { fetchPublicConfig, type PublicConfigModels } from '@/lib/publicConfig'

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
        const m = cfg?.models
        if (m && Array.isArray(m.options) && typeof m.default === 'string') {
          setModels({
            default: m.default || cfg?.defaults?.primary_model || DEFAULT_MODEL,
            options: m.options || [],
          })
        } else if (cfg?.defaults?.primary_model) {
          setModels({ default: cfg.defaults.primary_model, options: [cfg.defaults.primary_model] })
        } else {
          setModels(null)
        }
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

