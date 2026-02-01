'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { getApiBaseUrl } from '@/lib/api'
import { TimelineStep } from '@/components/visualization/ResearchTimeline'
import { TreeNode } from '@/components/visualization/ResearchTree'

type ResearchStatus = 'pending' | 'in_progress' | 'completed' | 'failed'

export interface ResearchProgress {
  timeline: TimelineStep[]
  tree: TreeNode | null
  stats: {
    totalSources: number
    searchQueries: number
    elapsedTime: string
    status: ResearchStatus
  }
  isConnected: boolean
  error: string | null
}

interface UseResearchProgressOptions {
  threadId: string | null
  enabled?: boolean
}

export function useResearchProgress({
  threadId,
  enabled = true,
}: UseResearchProgressOptions): ResearchProgress {
  const [timeline, setTimeline] = useState<TimelineStep[]>([])
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [stats, setStats] = useState<{
    totalSources: number
    searchQueries: number
    elapsedTime: string
    status: ResearchStatus
  }>({
    totalSources: 0,
    searchQueries: 0,
    elapsedTime: '0s',
    status: 'pending',
  })
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const eventSourceRef = useRef<EventSource | null>(null)
  const startTimeRef = useRef<number>(Date.now())

  // Update elapsed time
  useEffect(() => {
    if (stats.status !== 'in_progress') return

    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000)
      const minutes = Math.floor(elapsed / 60)
      const seconds = elapsed % 60
      setStats(prev => ({
        ...prev,
        elapsedTime: minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`,
      }))
    }, 1000)

    return () => clearInterval(interval)
  }, [stats.status])

  // SSE connection
  useEffect(() => {
    if (!threadId || !enabled) {
      return
    }

    const url = `${getApiBaseUrl()}/api/events/${threadId}`

    try {
      const eventSource = new EventSource(url)
      eventSourceRef.current = eventSource

      eventSource.onopen = () => {
        setIsConnected(true)
        setError(null)
        startTimeRef.current = Date.now()
      }

      eventSource.onerror = () => {
        setIsConnected(false)
        setError('Connection lost')
      }

      // Handle different event types
      eventSource.addEventListener('research_node_start', (e) => {
        try {
          const data = JSON.parse(e.data)
          addTimelineStep({
            id: data.node_id || `step-${Date.now()}`,
            title: data.topic || 'Researching...',
            status: 'in_progress',
            timestamp: new Date().toLocaleTimeString(),
          })
          setStats(prev => ({ ...prev, status: 'in_progress' }))
        } catch (err) {
          console.error('Failed to parse research_node_start:', err)
        }
      })

      eventSource.addEventListener('research_node_complete', (e) => {
        try {
          const data = JSON.parse(e.data)
          updateTimelineStep(data.node_id, {
            status: 'completed',
            sources: data.sources,
            description: data.summary,
          })
          setStats(prev => ({
            ...prev,
            totalSources: prev.totalSources + (data.sources?.length || 0),
          }))
        } catch (err) {
          console.error('Failed to parse research_node_complete:', err)
        }
      })

      eventSource.addEventListener('search', (e) => {
        try {
          const data = JSON.parse(e.data)
          setStats(prev => ({
            ...prev,
            searchQueries: prev.searchQueries + 1,
          }))
          if (data.results?.length) {
            setStats(prev => ({
              ...prev,
              totalSources: prev.totalSources + data.results.length,
            }))
          }
        } catch (err) {
          console.error('Failed to parse search event:', err)
        }
      })

      eventSource.addEventListener('research_tree_update', (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.tree) {
            setTree(data.tree)
          }
        } catch (err) {
          console.error('Failed to parse research_tree_update:', err)
        }
      })

      eventSource.addEventListener('complete', () => {
        setStats(prev => ({ ...prev, status: 'completed' }))
      })

      eventSource.addEventListener('error', (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data)
          setError(data.message || 'Research failed')
          setStats(prev => ({ ...prev, status: 'failed' }))
        } catch {
          // Ignore parse errors for error events
        }
      })

      return () => {
        eventSource.close()
        eventSourceRef.current = null
      }
    } catch (err) {
      setError('Failed to connect to event stream')
      console.error('SSE connection error:', err)
    }
  }, [threadId, enabled])

  const addTimelineStep = useCallback((step: TimelineStep) => {
    setTimeline(prev => [...prev, step])
  }, [])

  const updateTimelineStep = useCallback((id: string, updates: Partial<TimelineStep>) => {
    setTimeline(prev =>
      prev.map(step =>
        step.id === id ? { ...step, ...updates } : step
      )
    )
  }, [])

  return {
    timeline,
    tree,
    stats,
    isConnected,
    error,
  }
}
