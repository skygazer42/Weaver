'use client'

import React, { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight, Circle } from 'lucide-react'

export interface TreeNode {
  id: string
  topic: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  depth: number
  children: TreeNode[]
  summary?: string
  sources?: string[]
}

interface ResearchTreeProps {
  root: TreeNode | null
  onNodeClick?: (node: TreeNode) => void
  className?: string
}

export function ResearchTree({ root, onNodeClick, className }: ResearchTreeProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set(['root']))

  const toggleExpand = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setExpandedIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }, [])

  if (!root) {
    return (
      <div className={cn("text-center text-muted-foreground py-8", className)}>
        No research tree available
      </div>
    )
  }

  const renderNode = (node: TreeNode) => {
    const isExpanded = expandedIds.has(node.id)
    const hasChildren = node.children && node.children.length > 0

    const statusColors = {
      pending: 'bg-yellow-500',
      in_progress: 'bg-primary',
      completed: 'bg-green-500',
      failed: 'bg-red-500',
    }

    const statusLeftBorderColors = {
      pending: 'border-l-yellow-500/40',
      in_progress: 'border-l-primary/40',
      completed: 'border-l-green-500/40',
      failed: 'border-l-red-500/40',
    }

    return (
      <div key={node.id} className="relative">
        {/* Node Card */}
        <div
          className={cn(
            "relative flex items-start gap-3 p-3 rounded-xl cursor-pointer border border-border/60 border-l-4 bg-card transition-colors duration-200 hover:bg-accent",
            statusLeftBorderColors[node.status],
          )}
          onClick={() => onNodeClick?.(node)}
        >
          {/* Expand/Collapse Button */}
          {hasChildren && (
            <button
              type="button"
              onClick={(e) => toggleExpand(node.id, e)}
              className="flex-shrink-0 p-1 rounded hover:bg-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          )}

          {!hasChildren && (
            <div className="flex-shrink-0 p-1">
              <Circle className="h-4 w-4 text-muted-foreground/30" />
            </div>
          )}

          {/* Status Indicator */}
          <div className={cn("flex-shrink-0 mt-1.5 h-2 w-2 rounded-full", statusColors[node.status])} />

          {/* Content */}
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-sm truncate">{node.topic}</h4>
            {node.summary && (
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                {node.summary}
              </p>
            )}
            {node.sources && node.sources.length > 0 && (
              <div className="flex items-center gap-1 mt-2">
                <span className="text-xs text-muted-foreground">
                  {node.sources.length} sources
                </span>
              </div>
            )}
          </div>

          {/* Depth Badge */}
          <div className="flex-shrink-0">
            <span className="text-xs text-muted-foreground/50">
              L{node.depth}
            </span>
          </div>
        </div>

        {/* Children */}
        {hasChildren && isExpanded && (
          <div className="pl-6 mt-2 space-y-2 border-l border-dashed border-border/60 ml-4">
            {node.children.map(child => renderNode(child))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={cn("space-y-2", className)}>
      {renderNode(root)}
    </div>
  )
}
