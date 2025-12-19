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
      const defaultHistory = [
        { id: '1', title: 'Market Analysis 2024', date: 'Today' },
        { id: '2', title: 'Python Viz Script', date: 'Yesterday' }
      ]
      setHistory(defaultHistory)
      
      // Populate dummy messages for demo if not present
      if (!localStorage.getItem('session_1')) {
          localStorage.setItem('session_1', JSON.stringify([
              { id: 'm1', role: 'user', content: 'Analyze the market trends for AI agents in 2024.' },
              { id: 'm2', role: 'assistant', content: 'Based on recent reports, the AI agent market is projected to grow significantly...' }
          ]))
      }
      if (!localStorage.getItem('session_2')) {
          localStorage.setItem('session_2', JSON.stringify([
              { id: 'm3', role: 'user', content: 'Write a python script to visualize this CSV data.' },
              { id: 'm4', role: 'assistant', content: 'Here is a matplotlib script to visualize your data:\n```python\nimport pandas as pd\nimport matplotlib.pyplot as plt\n...```' }
          ]))
      }
    }
    setIsHistoryLoading(false)
  }, [])

  // Save History to LocalStorage with debounce
  useEffect(() => {
    if (!isHistoryLoading) {
      const timeoutId = setTimeout(() => {
        localStorage.setItem(STORAGE_KEYS.HISTORY, JSON.stringify(history))
      }, 1000)
      return () => clearTimeout(timeoutId)
    }
  }, [history, isHistoryLoading])

  const saveToHistory = (messages: Message[]) => {
    if (messages.length > 0) {
      const firstUserMsg = messages.find(m => m.role === 'user')
      const title = firstUserMsg ? firstUserMsg.content.slice(0, 30) : 'New Conversation'
      const id = Date.now().toString()
      
      const newSession: ChatSession = {
        id,
        title: title,
        date: 'Just now'
      }
      setHistory(prev => [newSession, ...prev])
      
      // Save messages for this session
      localStorage.setItem(`session_${id}`, JSON.stringify(messages))
    }
  }

  const loadSession = (id: string): Message[] | null => {
    const data = localStorage.getItem(`session_${id}`)
    if (data) {
      try {
        return JSON.parse(data)
      } catch (e) {
        console.error('Failed to parse session messages', e)
      }
    }
    return null
  }

  const deleteSession = (id: string) => {
    setHistory(prev => prev.filter(s => s.id !== id))
    localStorage.removeItem(`session_${id}`)
  }

  const clearHistory = () => {
    // Clear all session data
    history.forEach(session => {
        localStorage.removeItem(`session_${session.id}`)
    })
    setHistory([])
    localStorage.removeItem(STORAGE_KEYS.HISTORY)
  }

  return {
    history,
    setHistory,
    isHistoryLoading,
    saveToHistory,
    loadSession,
    deleteSession,
    clearHistory
  }
}
