// Simple request cache with TTL for reducing redundant API calls

interface CacheEntry {
  data: any
  timestamp: number
}

const requestCache = new Map<string, CacheEntry>()

// Default cache TTL: 5 seconds
const DEFAULT_TTL = 5000

// Max cache entries to prevent memory bloat
const MAX_CACHE_SIZE = 100

function generateCacheKey(url: string, options?: RequestInit): string {
  const body = options?.body ? JSON.stringify(options.body) : ''
  const method = options?.method || 'GET'
  return `${method}:${url}:${body}`
}

function cleanupExpiredEntries(ttl: number): void {
  const now = Date.now()
  const expiredKeys: string[] = []

  requestCache.forEach((entry, key) => {
    if (now - entry.timestamp > ttl) {
      expiredKeys.push(key)
    }
  })

  expiredKeys.forEach(key => requestCache.delete(key))
}

function evictOldestEntries(): void {
  if (requestCache.size <= MAX_CACHE_SIZE) return

  // Convert to array and sort by timestamp
  const entries = Array.from(requestCache.entries())
    .sort((a, b) => a[1].timestamp - b[1].timestamp)

  // Remove oldest entries until under limit
  const toRemove = entries.slice(0, entries.length - MAX_CACHE_SIZE)
  toRemove.forEach(([key]) => requestCache.delete(key))
}

/**
 * Cached fetch wrapper that stores responses for a short TTL
 * to prevent duplicate requests for the same data
 */
export async function cachedFetch<T = any>(
  url: string,
  options?: RequestInit,
  ttl: number = DEFAULT_TTL
): Promise<T> {
  const cacheKey = generateCacheKey(url, options)
  const now = Date.now()

  // Check cache
  const cached = requestCache.get(cacheKey)
  if (cached && now - cached.timestamp < ttl) {
    return cached.data as T
  }

  // Make request
  const response = await fetch(url, options)

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }

  const data = await response.json()

  // Store in cache
  requestCache.set(cacheKey, { data, timestamp: now })

  // Cleanup
  evictOldestEntries()
  cleanupExpiredEntries(ttl * 2) // Keep entries a bit longer for potential hits

  return data as T
}

/**
 * Invalidate cache entries matching a URL pattern
 */
export function invalidateCache(urlPattern?: string): void {
  if (!urlPattern) {
    requestCache.clear()
    return
  }

  requestCache.forEach((_, key) => {
    if (key.includes(urlPattern)) {
      requestCache.delete(key)
    }
  })
}

/**
 * Get cache statistics for debugging
 */
export function getCacheStats(): { size: number; keys: string[] } {
  return {
    size: requestCache.size,
    keys: Array.from(requestCache.keys())
  }
}
