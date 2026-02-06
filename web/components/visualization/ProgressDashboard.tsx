'use client'

import React, { useState } from 'react'
import { cn } from '@/lib/utils'
import { Clock, GitBranch, BarChart3, FileText } from 'lucide-react'
import { ResearchTimeline, TimelineStep } from './ResearchTimeline'
import { ResearchTree, TreeNode } from './ResearchTree'
import { QualityBadge } from './QualityBadge'

interface ProgressDashboardProps {
  timeline?: TimelineStep[]
  tree?: TreeNode | null
  stats?: {
    totalSources: number
    searchQueries: number
    elapsedTime: string
    status: 'pending' | 'in_progress' | 'completed' | 'failed'
    quality?: {
      coverage: number
      citation: number
      consistency: number
    }
  }
  className?: string
}

type TabType = 'timeline' | 'tree' | 'stats'

export function ProgressDashboard({
  timeline = [],
  tree = null,
  stats,
  className,
}: ProgressDashboardProps) {
  const [activeTab, setActiveTab] = useState<TabType>('timeline')

  const tabs = [
    { id: 'timeline' as TabType, label: 'Timeline', icon: Clock },
    { id: 'tree' as TabType, label: 'Research Tree', icon: GitBranch },
    { id: 'stats' as TabType, label: 'Statistics', icon: BarChart3 },
  ]

  const statusColors = {
    pending: 'text-yellow-500',
    in_progress: 'text-blue-500',
    completed: 'text-green-500',
    failed: 'text-red-500',
  }

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header with Stats Summary */}
      {stats && (
        <div className="flex items-center gap-4 p-4 border-b bg-gradient-to-r from-muted/30 to-transparent">
          <div className="flex items-center gap-2">
            <div className={cn("status-indicator", stats.status)} />
            <span className={cn("text-sm font-medium capitalize", statusColors[stats.status])}>
              {stats.status.replace('_', ' ')}
            </span>
          </div>
          <div className="flex-1 flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <FileText className="h-4 w-4" />
              {stats.totalSources} sources
            </span>
            <span className="flex items-center gap-1">
              <BarChart3 className="h-4 w-4" />
              {stats.searchQueries} queries
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-4 w-4" />
              {stats.elapsedTime}
            </span>
          </div>
          {stats.quality && (
            <div className="flex items-center gap-2">
              <QualityBadge label="Coverage" value={stats.quality.coverage} />
              <QualityBadge label="Citation" value={stats.quality.citation} />
              <QualityBadge label="Consistency" value={stats.quality.consistency} />
            </div>
          )}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex items-center gap-1 p-2 border-b">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all duration-200",
                activeTab === tab.id
                  ? "bg-gradient-to-r from-blue-500/10 to-purple-500/10 text-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              )}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto p-4">
        {activeTab === 'timeline' && (
          <ResearchTimeline steps={timeline} />
        )}

        {activeTab === 'tree' && (
          <ResearchTree root={tree} />
        )}

        {activeTab === 'stats' && stats && (
          <div className="grid grid-cols-2 gap-4">
            <StatCard
              label="Total Sources"
              value={stats.totalSources.toString()}
              icon={FileText}
              color="blue"
            />
            <StatCard
              label="Search Queries"
              value={stats.searchQueries.toString()}
              icon={BarChart3}
              color="purple"
            />
            <StatCard
              label="Elapsed Time"
              value={stats.elapsedTime}
              icon={Clock}
              color="green"
            />
            <StatCard
              label="Status"
              value={stats.status.replace('_', ' ')}
              icon={GitBranch}
              color={stats.status === 'completed' ? 'green' : stats.status === 'failed' ? 'red' : 'blue'}
            />
            {stats.quality && (
              <div className="col-span-2 rounded-xl border bg-gradient-to-r from-slate-500/5 to-slate-500/10 p-4">
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Quality Signals
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <QualityBadge label="Coverage" value={stats.quality.coverage} />
                  <QualityBadge label="Citation" value={stats.quality.citation} />
                  <QualityBadge label="Consistency" value={stats.quality.consistency} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

interface StatCardProps {
  label: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  color: 'blue' | 'purple' | 'green' | 'red'
}

function StatCard({ label, value, icon: Icon, color }: StatCardProps) {
  const colorClasses = {
    blue: 'from-blue-500/10 to-blue-500/5 border-blue-500/20',
    purple: 'from-purple-500/10 to-purple-500/5 border-purple-500/20',
    green: 'from-green-500/10 to-green-500/5 border-green-500/20',
    red: 'from-red-500/10 to-red-500/5 border-red-500/20',
  }

  const iconColors = {
    blue: 'text-blue-500',
    purple: 'text-purple-500',
    green: 'text-green-500',
    red: 'text-red-500',
  }

  return (
    <div className={cn(
      "p-4 rounded-xl border bg-gradient-to-br",
      colorClasses[color]
    )}>
      <div className="flex items-center gap-3">
        <Icon className={cn("h-5 w-5", iconColors[color])} />
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-semibold capitalize">{value}</p>
        </div>
      </div>
    </div>
  )
}
