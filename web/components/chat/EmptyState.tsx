'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { Search, Bot, BrainCircuit } from 'lucide-react'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  selectedMode: string
  onModeSelect: (mode: string) => void
}

export function EmptyState({ selectedMode, onModeSelect }: EmptyStateProps) {
  const modes = [
    {
      id: 'web',
      label: 'Web Search',
      icon: Search,
      description: 'Fast internet search for quick answers'
    },
    {
      id: 'agent',
      label: 'Agent',
      icon: Bot,
      description: 'Reasoning agent with tool use'
    },
    {
      id: 'deep',
      label: 'Deep Search',
      icon: BrainCircuit,
      description: 'Comprehensive research with multiple steps'
    }
  ]

  return (
    <div className="flex flex-col items-center justify-center h-full max-w-2xl mx-auto p-4 space-y-8">
      <div className="flex flex-col items-center space-y-2">
        <div className="h-16 w-16 bg-primary text-primary-foreground rounded-2xl flex items-center justify-center text-3xl font-bold">
          M
        </div>
        <h2 className="text-2xl font-bold">How can I help you today?</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full">
        {modes.map((mode) => (
          <button
            key={mode.id}
            onClick={() => onModeSelect(mode.id)}
            className={cn(
              "flex flex-col items-center p-4 rounded-xl border-2 transition-all hover:bg-muted/50",
              selectedMode === mode.id 
                ? "border-primary bg-primary/5 ring-1 ring-primary" 
                : "border-transparent bg-muted/20 hover:border-primary/20"
            )}
          >
            <mode.icon className={cn(
              "h-8 w-8 mb-3",
              selectedMode === mode.id ? "text-primary" : "text-muted-foreground"
            )} />
            <span className="font-semibold text-sm mb-1">{mode.label}</span>
            <span className="text-xs text-center text-muted-foreground">
              {mode.description}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
