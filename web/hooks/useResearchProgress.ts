'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { getApiBaseUrl } from '@/lib/api'
import { TimelineStep } from '@/components/visualization/ResearchTimeline'
import { TreeNode } from '@/components/visualization/ResearchTree'
import { ResearchQualityMetrics } from '@/types/chat'

type ResearchStatus = 'pending' | 'in_progress' | 'completed' | 'failed'

export interface ResearchProgress {
  timeline: TimelineStep[]
  tree: TreeNode | null
  stats: {
    totalSources: number
    searchQueries: number
    elapsedTime: string
    status: ResearchStatus
    quality?: ResearchQualityMetrics
  }
  isConnected: boolean
  error: string | null
}

interface UseResearchProgressOptions {
  threadId: string | null
  enabled?: boolean
}

function parseEventPayload(raw: string): any {
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && parsed.data && typeof parsed.data === 'object') {
      return parsed.data
    }
    return parsed
  } catch {
    return {}
  }
}

export function useResearchProgress({
  threadId,
  enabled = true,
}: UseResearchProgressOptions): ResearchProgress {
  const normalizeQuality = useCallback((raw: any): ResearchQualityMetrics | null => {
    if (!raw || typeof raw !== 'object') {
      return null
    }
    const asNumber = (value: any, fallback = 0): number =>
      Number.isFinite(Number(value)) ? Math.max(0, Math.min(1, Number(value))) : fallback

    const queryCoverage = asNumber(raw.queryCoverage ?? raw.query_coverage_score ?? raw.query_coverage?.score, -1)
    const freshness = asNumber(raw.freshness ?? raw.fresh_30_ratio ?? raw.freshness_summary?.fresh_30_ratio, -1)

    return {
      coverage: asNumber(raw.coverage ?? (queryCoverage >= 0 ? queryCoverage : 0)),
      citation: asNumber(raw.citation ?? raw.citation_coverage ?? raw.accuracy),
      consistency: asNumber(raw.consistency ?? raw.contradiction_free ?? raw.coherence),
      freshness: freshness >= 0 ? freshness : undefined,
      queryCoverage: queryCoverage >= 0 ? queryCoverage : undefined,
    }
  }, [])

  const mergeQuality = useCallback((raw: any) => {
    const normalized = normalizeQuality(raw)
    if (!normalized) {
      return
    }
    setStats(prev => ({
      ...prev,
      quality: normalized,
    }))
  }, [normalizeQuality])

  const [timeline, setTimeline] = useState<TimelineStep[]>([])
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [stats, setStats] = useState<{
    totalSources: number
    searchQueries: number
    elapsedTime: string
    status: ResearchStatus
    quality?: ResearchQualityMetrics
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
          const data = parseEventPayload(e.data)
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
          const data = parseEventPayload(e.data)
          updateTimelineStep(data.node_id, {
            status: 'completed',
            sources: data.sources,
            description: data.summary,
          })
          mergeQuality(data.quality || data.eval_dimensions)
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
          const data = parseEventPayload(e.data)
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
          const data = parseEventPayload(e.data)
          if (data.tree) {
            setTree(data.tree)
          }
          mergeQuality(data.quality || data.eval_dimensions)
        } catch (err) {
          console.error('Failed to parse research_tree_update:', err)
        }
      })

      eventSource.addEventListener('quality_update', (e) => {
        try {
          const data = parseEventPayload(e.data)
          mergeQuality(data)
        } catch (err) {
          console.error('Failed to parse quality_update:', err)
        }
      })

      eventSource.addEventListener('complete', () => {
        setStats(prev => ({ ...prev, status: 'completed' }))
      })

      eventSource.addEventListener('error', (e) => {
        try {
          const data = parseEventPayload((e as MessageEvent).data)
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
  }, [threadId, enabled, mergeQuality])

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
