'use client'

import { useState, useEffect, useCallback } from 'react'
import { ChatSession, Message } from '@/types/chat'
import { StorageService } from '@/lib/storage-service'

export function useChatHistory(workspaceId?: string) {
  const [history, setHistory] = useState<ChatSession[]>([])
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)

  // Load History
  useEffect(() => {
    const loadHistory = () => {
      try {
        const savedHistory = StorageService.getHistory<ChatSession>(workspaceId)
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
  }, [workspaceId])

  // Persist changes whenever history updates
  useEffect(() => {
    if (!isHistoryLoading) {
      StorageService.saveHistory(history, workspaceId)
    }
  }, [history, isHistoryLoading, workspaceId])

  const refreshHistory = useCallback(() => {
    const saved = StorageService.getHistory<ChatSession>(workspaceId)
    setHistory(saved)
  }, [workspaceId])

  const saveToHistory = useCallback((messages: Message[], currentSessionId?: string, searchMode?: string) => {
    if (messages.length === 0) return null

    const timestamp = Date.now()
    const sessionId = currentSessionId || (workspaceId ? `${workspaceId}-${timestamp}` : timestamp.toString())

    setHistory(prev => {
      const existingIndex = prev.findIndex(s => s.id === sessionId)
      
      if (existingIndex !== -1) {
        // Update existing session
        const updatedHistory = [...prev]
        updatedHistory[existingIndex] = {
          ...updatedHistory[existingIndex],
          updatedAt: timestamp,
          searchMode: searchMode ?? updatedHistory[existingIndex].searchMode,
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
        // Create new session
        const firstUserMsg = messages.find(m => m.role === 'user')
        const title = firstUserMsg ? firstUserMsg.content.slice(0, 40) : 'New Conversation'
        
        const newSession: ChatSession = {
          id: sessionId,
          title,
          date: new Date(timestamp).toLocaleDateString(), // Keep legacy for display fallback
          createdAt: timestamp,
          updatedAt: timestamp,
          isPinned: false,
          searchMode,
          tags: []
        }
        return [newSession, ...prev]
      }
    })

    // Save messages content
    StorageService.saveSessionMessages(sessionId, messages, workspaceId)
    
    return sessionId
  }, [workspaceId])

  const loadSession = (id: string): Message[] | null => {
    return StorageService.getSessionMessages<Message>(id, workspaceId)
  }

  const deleteSession = (id: string) => {
    setHistory(prev => prev.filter(s => s.id !== id))
    StorageService.removeSessionMessages(id, workspaceId)
  }

  const clearHistory = () => {
    StorageService.clearAll(workspaceId)
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
