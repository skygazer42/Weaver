'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { ArrowRight, Sparkles, TrendingUp, Code2, BookOpen } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  selectedMode: string
  onModeSelect: (mode: string) => void // Kept for compatibility but might be unused if pills are primary
}

export function EmptyState({ selectedMode, onModeSelect }: EmptyStateProps) {
  const { t } = useI18n()

  const starters = [
    {
      icon: TrendingUp,
      text: t('starterAnalyze'),
      mode: "deep"
    },
    {
      icon: Code2,
      text: t('starterWrite'),
      mode: "agent"
    },
    {
      icon: BookOpen,
      text: t('starterSummarize'),
      mode: "web"
    },
    {
      icon: Sparkles,
      text: t('starterPlan'),
      mode: "agent"
    }
  ]

  return (
    <div className="flex flex-col items-center justify-center h-full w-full max-w-4xl mx-auto p-6 animate-in fade-in zoom-in-95 duration-500">
      
      {/* Hero Section */}
      <div className="flex flex-col items-center space-y-6 mb-12 text-center">
        <div className="relative group cursor-default">
            <div className="absolute inset-0 bg-primary/20 rounded-3xl blur-xl group-hover:blur-2xl transition-all duration-500 opacity-50" />
            <div className="relative h-24 w-24 rounded-3xl flex items-center justify-center shadow-xl shadow-primary/20 ring-1 ring-white/20 overflow-hidden bg-white">
              <img src="/logo.png" alt="Weaver" className="h-20 w-20 object-contain" />
            </div>
        </div>
        
        <div className="space-y-2 max-w-lg">
            <h2 className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-b from-foreground to-foreground/70">
                {t('emptyStateTitle')}
            </h2>
            <p className="text-muted-foreground text-lg">
                {t('emptyStateSubtitle')} <br className="hidden sm:block"/>
                {t('emptyStateDescription')}
            </p>
        </div>
      </div>

      {/* Starter Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
        {starters.map((starter, i) => (
          <button
            key={i}
            onClick={() => {
                // In a real app, this would populate input
                const input = document.querySelector('input') as HTMLInputElement
                if (input) {
                    input.value = starter.text
                    input.focus()
                    // Dispatch change event manually for React state? 
                    // Simplified: We assume user types or this component accepts onSelect prop to bubble up
                }
            }}
            className="group flex items-start gap-4 p-4 rounded-xl border bg-card/50 hover:bg-card hover:shadow-md hover:border-primary/20 transition-all duration-300 text-left"
          >
            <div className="p-2 rounded-lg bg-muted group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                <starter.icon className="h-5 w-5" />
            </div>
            <div className="flex-1 space-y-1">
                <p className="text-sm font-medium leading-snug group-hover:text-primary transition-colors">
                    {starter.text}
                </p>
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground uppercase tracking-wider font-semibold opacity-0 group-hover:opacity-100 transition-opacity translate-y-2 group-hover:translate-y-0">
                    <span>{t('useMode')} {starter.mode} {t('mode')}</span>
                    <ArrowRight className="h-3 w-3" />
                </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}