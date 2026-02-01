'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { ChatSession, Message } from '@/types/chat'
import { StorageService } from '@/lib/storage-service'

// Smart title generation from message content
function generateSmartTitle(content: string): string {
  if (!content) return 'New Conversation'

  // Clean markdown and special characters
  const clean = content
    .replace(/```[\s\S]*?```/g, '') // Remove code blocks
    .replace(/`[^`]+`/g, '') // Remove inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // Links -> text
    .replace(/[#*_~\[\]]/g, '') // Remove markdown symbols
    .replace(/https?:\/\/\S+/g, '') // Remove URLs
    .replace(/\n+/g, ' ') // Newlines to spaces
    .trim()

  if (!clean) return 'New Conversation'

  // Extract meaningful words (skip common filler words)
  const stopWords = new Set(['the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'can', 'i', 'you', 'he', 'she', 'it', 'we',
    'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our',
    'their', 'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom',
    'how', 'when', 'where', 'why', 'please', 'help', 'want', 'need', 'like', 'just'])

  const words = clean
    .split(/\s+/)
    .filter(w => w.length > 2 && !stopWords.has(w.toLowerCase()))
    .slice(0, 6) // Take first 6 meaningful words

  if (words.length === 0) {
    // Fallback to first N characters
    return clean.length > 40 ? clean.slice(0, 37) + '...' : clean
  }

  const title = words.join(' ')
  return title.length > 50 ? title.slice(0, 47) + '...' : title
}

export function useChatHistory() {
  const [history, setHistory] = useState<ChatSession[]>([])
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)

  // Debounce timer for localStorage persistence
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null)
  const historyRef = useRef<ChatSession[]>(history)

  // Keep ref in sync
  useEffect(() => {
    historyRef.current = history
  }, [history])

  // Load History
  useEffect(() => {
    const loadHistory = () => {
      try {
        const savedHistory = StorageService.getHistory<ChatSession>()
        // Migrate legacy data if necessary
        const migratedHistory = savedHistory.map(session => ({
          ...session,
          createdAt: session.createdAt || Date.now(),
          updatedAt: session.updatedAt || Date.now(),
          isPinned: session.isPinned || false,
          tags: session.tags || []
        }))

        // Sort: Pinned first, then by updatedAt desc
        const sorted = migratedHistory.sort((a, b) => {
          if (a.isPinned && !b.isPinned) return -1
          if (!a.isPinned && b.isPinned) return 1
          return b.updatedAt - a.updatedAt
        })

        setHistory(sorted)
      } catch (e) {
        console.error('Failed to load history', e)
      } finally {
        setIsHistoryLoading(false)
      }
    }

    loadHistory()
  }, [])

  // Debounced persistence - only save every 2 seconds to avoid localStorage thrashing
  useEffect(() => {
    if (isHistoryLoading) return

    // Clear existing timer
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current)
    }

    // Set new timer
    saveTimerRef.current = setTimeout(() => {
      StorageService.saveHistory(historyRef.current)
    }, 2000)

    // Cleanup
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
      }
    }
  }, [history, isHistoryLoading])

  const refreshHistory = useCallback(() => {
    const saved = StorageService.getHistory<ChatSession>()
    setHistory(saved)
  }, [])

  const saveToHistory = (messages: Message[], currentSessionId?: string) => {
    if (messages.length === 0) return null

    const timestamp = Date.now()
    let sessionId = currentSessionId

    setHistory(prev => {
      const existingIndex = sessionId ? prev.findIndex(s => s.id === sessionId) : -1

      if (existingIndex !== -1) {
        // Update existing session
        const updatedHistory = [...prev]
        updatedHistory[existingIndex] = {
          ...updatedHistory[existingIndex],
          updatedAt: timestamp,
          // Update title if it's still the default "New Conversation" or generic
          // (Logic can be refined, here we just update timestamp primarily)
        }
        // Re-sort
        return updatedHistory.sort((a, b) => {
           if (a.isPinned && !b.isPinned) return -1
           if (!a.isPinned && b.isPinned) return 1
           return b.updatedAt - a.updatedAt
        })
      } else {
        // Create new session with smart title
        sessionId = sessionId || timestamp.toString()
        const firstUserMsg = messages.find(m => m.role === 'user')
        const title = firstUserMsg
          ? generateSmartTitle(firstUserMsg.content)
          : 'New Conversation'

        const newSession: ChatSession = {
          id: sessionId,
          title,
          date: new Date(timestamp).toLocaleDateString(), // Keep legacy for display fallback
          createdAt: timestamp,
          updatedAt: timestamp,
          isPinned: false,
          tags: []
        }
        return [newSession, ...prev]
      }
    })

    // Save messages content
    if (sessionId) {
      StorageService.saveSessionMessages(sessionId, messages)
    }

    return sessionId
  }

  const loadSession = (id: string): Message[] | null => {
    return StorageService.getSessionMessages(id)
  }

  const deleteSession = (id: string) => {
    setHistory(prev => prev.filter(s => s.id !== id))
    StorageService.removeSessionMessages(id)
  }

  const clearHistory = () => {
    StorageService.clearAll()
    setHistory([])
  }

  const togglePin = (id: string) => {
    setHistory(prev => {
      const mapped = prev.map(s => s.id === id ? { ...s, isPinned: !s.isPinned } : s)
      return mapped.sort((a, b) => {
          if (a.isPinned && !b.isPinned) return -1
          if (!a.isPinned && b.isPinned) return 1
          return b.updatedAt - a.updatedAt
      })
    })
  }

  const renameSession = (id: string, newTitle: string) => {
    setHistory(prev => prev.map(s => s.id === id ? { ...s, title: newTitle } : s))
  }

  const updateTags = (id: string, tags: string[]) => {
    setHistory(prev => prev.map(s => s.id === id ? { ...s, tags } : s))
  }

  return {
    history,
    isHistoryLoading,
    saveToHistory,
    loadSession,
    deleteSession,
    clearHistory,
    togglePin,
    renameSession,
    updateTags,
    refreshHistory
  }
}
