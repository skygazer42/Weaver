import { getApiBaseUrl } from '@/lib/api'
import { DEFAULT_MODEL } from '@/lib/constants'

export interface PublicConfigModels {
  default: string
  reasoning_default?: string
  options: string[]
  source?: 'siliconflow' | 'gateway' | 'static'
}

export interface PublicConfigResponse {
  version: string
  defaults: {
    port: number
    primary_model: string
    reasoning_model: string
  }
  features: Record<string, any>
  streaming: Record<string, any>
  models?: PublicConfigModels
}

let publicConfigPromise: Promise<PublicConfigResponse | null> | null = null

export function getPublicModels(config: PublicConfigResponse | null): PublicConfigModels | null {
  const models = config?.models
  if (models && Array.isArray(models.options) && typeof models.default === 'string') {
    return {
      default: models.default || config?.defaults.primary_model || DEFAULT_MODEL,
      reasoning_default: models.reasoning_default ?? config?.defaults.reasoning_model,
      options: models.options,
      source: models.source,
    }
  }
  if (config?.defaults.primary_model) {
    return {
      default: config.defaults.primary_model,
      reasoning_default: config.defaults.reasoning_model,
      options: [config.defaults.primary_model],
      source: 'static',
    }
  }
  return null
}

export async function fetchPublicConfig(): Promise<PublicConfigResponse | null> {
  if (!publicConfigPromise) {
    publicConfigPromise = fetch(`${getApiBaseUrl()}/api/config/public`, { cache: 'no-store' })
      .then(async (res) => {
        if (!res.ok) {
          publicConfigPromise = null
          return null
        }
        return (await res.json()) as PublicConfigResponse
      })
      .catch(() => {
        publicConfigPromise = null
        return null
      })
  }
  return publicConfigPromise
}

