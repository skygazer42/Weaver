export class StorageService {
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

  private static setItem<T>(key: string, value: T): boolean {
    if (typeof window === 'undefined') return false
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
      return true
    } catch (error) {
      console.error(`Error writing to localStorage key "${key}":`, error)
      return false
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
    return this.getItem<T[]>(`session_${sessionId}`) || []
  }

  static saveSessionMessages<T>(sessionId: string, messages: T[]): boolean {
    return this.setItem(`session_${sessionId}`, messages)
  }

  static getResearchId(sessionId: string): string | null {
    return this.getItem<string>('research_' + sessionId)
  }

  static setResearchId(sessionId: string, researchId: string | null): void {
    this.setItem('research_' + sessionId, researchId)
    if (researchId || this.getRecentResearchSession() === sessionId) {
      this.setItem('weaver-recent-research', researchId ? sessionId : null)
    }
  }

  static getRecentResearchSession(): string | null {
    return this.getItem<string>('weaver-recent-research')
  }

  static removeSessionMessages(sessionId: string): void {
    if (typeof window === 'undefined') return
    this.setResearchId(sessionId, null)
    window.localStorage.removeItem('research_' + sessionId)
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
        if (key.startsWith('session_') || key.startsWith('research_') || key === 'weaver-history' || key === 'weaver-artifacts' || key === 'weaver-recent-research') {
             if (!keysToKeep.includes(key)) {
                 window.localStorage.removeItem(key)
             }
        }
    })
  }
}
