import type { ChatRun } from '@/types/chat'

export class StorageService {
  private static key(key: string, workspaceId?: string): string {
    return workspaceId ? `weaver-project:${workspaceId}:${key}` : key
  }

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

  static getHistory<T>(workspaceId?: string): T[] {
    return this.getItem<T[]>(this.key('weaver-history', workspaceId)) || []
  }

  static saveHistory<T>(history: T[], workspaceId?: string): void {
    this.setItem(this.key('weaver-history', workspaceId), history)
  }

  static getArtifacts<T>(workspaceId?: string): T[] {
    return this.getItem<T[]>(this.key('weaver-artifacts', workspaceId)) || []
  }

  static saveArtifacts<T>(artifacts: T[], workspaceId?: string): void {
    this.setItem(this.key('weaver-artifacts', workspaceId), artifacts)
  }

  static getSessionMessages<T>(sessionId: string, workspaceId?: string): T[] {
    return this.getItem<T[]>(this.key('session_' + sessionId, workspaceId)) || []
  }

  static saveSessionMessages<T>(sessionId: string, messages: T[], workspaceId?: string): boolean {
    return this.setItem(this.key('session_' + sessionId, workspaceId), messages)
  }

  static getRun(sessionId: string, workspaceId?: string): ChatRun | null {
    const saved = this.getItem<ChatRun | string>(this.key('research_' + sessionId, workspaceId))
    return typeof saved === 'string' ? { id: saved, searchMode: 'ultra' } : saved
  }

  static setRun(sessionId: string, run: ChatRun | null, workspaceId?: string): void {
    this.setItem(this.key('research_' + sessionId, workspaceId), run)
    if (run || this.getRecentRunSession(workspaceId) === sessionId) {
      this.setItem(this.key('weaver-recent-research', workspaceId), run ? sessionId : null)
    }
  }

  static saveRunSnapshot(sessionId: string, run: ChatRun, workspaceId?: string): void {
    const saved = this.getRun(sessionId, workspaceId)
    if (saved?.id === run.id && (saved.lastEventId ?? 0) <= (run.lastEventId ?? 0)) {
      this.setItem(this.key('research_' + sessionId, workspaceId), run)
    }
  }

  static getRecentRunSession(workspaceId?: string): string | null {
    return this.getItem<string>(this.key('weaver-recent-research', workspaceId))
  }

  static markRunViewed(sessionId: string, workspaceId?: string): void {
    this.setItem(this.key('weaver-recent-research', workspaceId), sessionId)
  }

  static removeSessionMessages(sessionId: string, workspaceId?: string): void {
    if (typeof window === 'undefined') return
    this.setRun(sessionId, null, workspaceId)
    window.localStorage.removeItem(this.key('research_' + sessionId, workspaceId))
    window.localStorage.removeItem(this.key('session_' + sessionId, workspaceId))
  }

  static clearAll(workspaceId?: string): void {
    if (typeof window === 'undefined') return
    const projectPrefix = this.key('', workspaceId)
    for (const key of Object.keys(window.localStorage)) {
      const inScope = workspaceId
        ? key.startsWith(projectPrefix)
        : key.startsWith('session_') || key.startsWith('research_')
          || ['weaver-history', 'weaver-artifacts', 'weaver-recent-research'].includes(key)
      if (inScope) window.localStorage.removeItem(key)
    }
  }
}
