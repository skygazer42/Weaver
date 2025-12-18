'use client'

import { useState, useEffect } from 'react'
import { ChatSession, Message } from '@/types/chat'
import { STORAGE_KEYS } from '@/lib/constants'

export function useChatHistory() {
  const [history, setHistory] = useState<ChatSession[]>([])
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)

  // Load History from LocalStorage
  useEffect(() => {
    const savedHistory = localStorage.getItem(STORAGE_KEYS.HISTORY)
    if (savedHistory) {
      try {
        setHistory(JSON.parse(savedHistory))
      } catch (e) {
        console.error('Failed to parse history', e)
      }
    } else {
      // Default data for demo
      setHistory([
        { id: '1', title: 'Market Analysis 2024', date: 'Today' },
        { id: '2', title: 'Python Viz Script', date: 'Yesterday' }
      ])
    }
    setIsHistoryLoading(false)
  }, [])

  // Save History to LocalStorage
  useEffect(() => {
    if (!isHistoryLoading) {
      localStorage.setItem(STORAGE_KEYS.HISTORY, JSON.stringify(history))
    }
  }, [history, isHistoryLoading])

  const saveToHistory = (messages: Message[]) => {
    if (messages.length > 0) {
      const firstUserMsg = messages.find(m => m.role === 'user')
      const title = firstUserMsg ? firstUserMsg.content.slice(0, 30) : 'New Conversation'
      
      const newSession: ChatSession = {
        id: Date.now().toString(),
        title: title,
        date: 'Just now'
      }
      setHistory(prev => [newSession, ...prev])
    }
  }

  return {
    history,
    setHistory,
    isHistoryLoading,
    saveToHistory
  }
}
