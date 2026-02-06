export interface StorageUsage {
  used: number
  quota: number
  percentage: number
}

export interface CleanupResult {
  cleaned: boolean
  removed: number
  freedBytes: number
}

export class StorageService {
  // Estimated localStorage quota (5MB is typical)
  private static readonly ESTIMATED_QUOTA = 5 * 1024 * 1024

  private static getItem<T>(key: string): T | null {
    if (typeof window === 'undefined') return null
    try {
      const item = window.localStorage.getItem(key)
      return item ? (JSON.parse(item) as T) : null
    } catch (error) {
      console.error(`Error reading from localStorage key "${key}":`, error)
      return null
    }
  }

  private static setItem<T>(key: string, value: T): void {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch (error) {
      // Check if quota exceeded
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        console.warn('localStorage quota exceeded, attempting cleanup...')
        const result = this.cleanupOldSessions()
        if (result.cleaned) {
          // Retry after cleanup
          try {
            window.localStorage.setItem(key, JSON.stringify(value))
            return
          } catch {
            console.error('Still exceeded quota after cleanup')
          }
        }
      }
      console.error(`Error writing to localStorage key "${key}":`, error)
    }
  }

  /**
   * Get current storage usage statistics
   */
  static getStorageUsage(): StorageUsage {
    if (typeof window === 'undefined') {
      return { used: 0, quota: this.ESTIMATED_QUOTA, percentage: 0 }
    }

    let used = 0
    for (const key in localStorage) {
      if (localStorage.hasOwnProperty(key)) {
        // Each character in JavaScript is 2 bytes (UTF-16)
        used += (localStorage[key].length + key.length) * 2
      }
    }

    return {
      used,
      quota: this.ESTIMATED_QUOTA,
      percentage: (used / this.ESTIMATED_QUOTA) * 100
    }
  }

  /**
   * Check if storage usage exceeds threshold and cleanup if needed
   */
  static checkQuotaAndCleanup(thresholdPercent: number = 80): CleanupResult {
    const usage = this.getStorageUsage()
    if (usage.percentage > thresholdPercent) {
      return this.cleanupOldSessions()
    }
    return { cleaned: false, removed: 0, freedBytes: 0 }
  }

  /**
   * Cleanup sessions older than a specified age
   */
  static cleanupOldSessions(maxAgeDays: number = 30): CleanupResult {
    if (typeof window === 'undefined') {
      return { cleaned: false, removed: 0, freedBytes: 0 }
    }

    const usageBefore = this.getStorageUsage()
    const cutoff = Date.now() - maxAgeDays * 24 * 60 * 60 * 1000
    const history = this.getHistory<{ id: string; updatedAt?: number; createdAt?: number; isPinned?: boolean }>()

    // Filter to keep recent and pinned sessions
    const sessionsToRemove = history.filter(
      s => !s.isPinned && (s.updatedAt || s.createdAt || 0) < cutoff
    )

    if (sessionsToRemove.length === 0) {
      return { cleaned: false, removed: 0, freedBytes: 0 }
    }

    // Remove old session messages
    sessionsToRemove.forEach(s => {
      this.removeSessionMessages(s.id)
    })

    // Update history to only keep recent sessions
    const recentHistory = history.filter(
      s => s.isPinned || (s.updatedAt || s.createdAt || 0) >= cutoff
    )
    this.saveHistory(recentHistory)

    const usageAfter = this.getStorageUsage()

    return {
      cleaned: true,
      removed: sessionsToRemove.length,
      freedBytes: usageBefore.used - usageAfter.used
    }
  }

  static getHistory<T>(): T[] {
    return this.getItem<T[]>('weaver-history') || []
  }

  static saveHistory<T>(history: T[]): void {
    this.setItem('weaver-history', history)
  }

  static getArtifacts<T>(): T[] {
    return this.getItem<T[]>('weaver-artifacts') || []
  }

  static saveArtifacts<T>(artifacts: T[]): void {
    this.setItem('weaver-artifacts', artifacts)
  }

  static getSessionMessages<T>(sessionId: string): T[] {
    const messages = this.getItem<T[]>(`session_${sessionId}`) || []
    if (!Array.isArray(messages)) {
      return []
    }
    return this.normalizeSessionMessages(messages) as T[]
  }

  static saveSessionMessages<T>(sessionId: string, messages: T[]): void {
    const normalized = this.normalizeSessionMessages(messages)
    this.setItem(`session_${sessionId}`, normalized)
  }

  static removeSessionMessages(sessionId: string): void {
    if (typeof window === 'undefined') return
    window.localStorage.removeItem(`session_${sessionId}`)
  }

  static clearAll(keysToKeep: string[] = []): void {
    if (typeof window === 'undefined') return
    // Simple clear, in a real app might need more logic to only clear app-specific keys
    // For now we iterate known keys or just clear all
    // Strategy: Clear known main keys and iterate to find sessions

    // 1. Get all session IDs first to clean them up if needed, but localStorage.clear() does it all.
    // However, we might want to keep some settings.

    // For now, let's just clear the specific app keys we manage
    this.saveHistory([])
    this.saveArtifacts([])
    // Also need to find and remove session_ keys.
    // This is tricky without a list. We rely on the history list usually.
    // A robust way is to iterate all keys.
    Object.keys(window.localStorage).forEach(key => {
        if (key.startsWith('session_') || key === 'weaver-history' || key === 'weaver-artifacts') {
             if (!keysToKeep.includes(key)) {
                 window.localStorage.removeItem(key)
             }
        }
    })
  }

  private static normalizeSessionMessages<T>(messages: T[]): T[] {
    if (!Array.isArray(messages)) {
      return messages
    }
    return messages.map((message: any) => {
      if (!message || !Array.isArray(message.sources)) {
        return message
      }
      return {
        ...message,
        sources: message.sources.map((source: any) => this.normalizeSource(source)),
      }
    }) as T[]
  }

  private static normalizeSource(source: any): any {
    if (!source || typeof source !== 'object') {
      return source
    }

    const rawUrl = String(source.rawUrl || source.url || '').trim()
    const canonicalUrl = this.normalizeUrl(rawUrl)
    const publishedDate = source.publishedDate ? String(source.publishedDate) : undefined

    return {
      ...source,
      rawUrl: rawUrl || source.rawUrl || '',
      url: canonicalUrl || rawUrl || source.url,
      domain: source.domain || this.extractDomain(canonicalUrl || rawUrl),
      provider: source.provider || this.inferProvider(canonicalUrl || rawUrl),
      publishedDate,
      freshnessDays:
        source.freshnessDays ?? this.computeFreshnessDays(publishedDate),
    }
  }

  private static normalizeUrl(url: string): string {
    if (!url) return ''
    try {
      const parsed = new URL(url)
      parsed.hash = ''
      return parsed.toString()
    } catch {
      return url
    }
  }

  private static extractDomain(url: string): string {
    if (!url) return 'unknown'
    try {
      const parsed = new URL(url)
      return parsed.hostname.replace(/^www\\./, '')
    } catch {
      return 'unknown'
    }
  }

  private static inferProvider(url: string): string {
    const domain = this.extractDomain(url)
    if (domain.includes('arxiv')) return 'arxiv'
    if (domain.includes('pubmed')) return 'pubmed'
    if (domain.includes('github')) return 'github'
    if (domain.includes('reddit')) return 'reddit'
    if (domain.includes('news')) return 'news'
    return 'web'
  }

  private static computeFreshnessDays(dateText?: string): number | null {
    if (!dateText) return null
    const parsed = Date.parse(dateText)
    if (Number.isNaN(parsed)) return null
    const days = (Date.now() - parsed) / (1000 * 60 * 60 * 24)
    return Math.max(0, Number(days.toFixed(1)))
  }
}
