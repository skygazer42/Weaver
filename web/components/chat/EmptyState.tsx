'use client'

import React from 'react'
import Image from 'next/image'
import { ArrowRight, Sparkles, TrendingUp, Code2, BookOpen } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  selectedMode: string
  onModeSelect: (mode: string) => void
  onStarterClick?: (text: string, mode: string) => void
}

export function EmptyState({ selectedMode, onStarterClick }: EmptyStateProps) {
  const { t } = useI18n()

  const starters = [
    {
      icon: TrendingUp,
      text: t('starterAnalyze'),
      mode: "ultra",
      label: t('ultra'),
    },
    {
      icon: Code2,
      text: t('starterWrite'),
      mode: "agent",
      label: t('agent'),
    },
    {
      icon: BookOpen,
      text: t('starterSummarize'),
      mode: "web",
      label: t('web'),
    },
    {
      icon: Sparkles,
      text: t('starterPlan'),
      mode: "direct",
      label: t('direct'),
    }
  ]

  return (
    <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col items-center justify-center px-2 py-8 sm:px-6 sm:py-12">
      
      {/* Hero Section */}
      <div className="mb-8 flex flex-col items-center gap-5 text-center sm:mb-10">
        <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl border border-border/80 bg-white shadow-surface">
          <Image src="/logo.png" alt="Weaver" width={52} height={52} priority className="object-contain" />
        </div>
        
        <div className="space-y-2 max-w-lg">
            <h2 className="text-balance text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                {t('emptyStateTitle')}
            </h2>
            <p className="text-balance text-sm leading-6 text-muted-foreground sm:text-base">
                {t('emptyStateSubtitle')} <br className="hidden sm:block"/>
                {t('emptyStateDescription')}
            </p>
        </div>
      </div>

      {/* Starter Grid */}
      <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        {starters.map((starter, i) => (
          <button
            key={i}
            type="button"
            onClick={() => {
                if (onStarterClick) {
                    onStarterClick(starter.text, starter.mode)
                }
            }}
            className="group flex items-start gap-3 rounded-lg border border-border/80 bg-card p-4 text-left shadow-xs transition-[border-color,box-shadow] hover:border-primary/35 hover:shadow-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-2"
          >
            <div className="rounded-md border border-border/70 bg-surface-subtle p-2 text-muted-foreground transition-colors group-hover:text-primary">
                <starter.icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1 space-y-3">
                <p className="text-sm font-medium leading-snug group-hover:text-primary transition-colors">
                    {starter.text}
                </p>
                <div className="flex items-center justify-between gap-2">
                    <span className={cn("rounded-md border px-1.5 py-0.5 text-[11px] font-medium", selectedMode === starter.mode ? "border-primary/20 bg-primary/10 text-primary" : "border-border/70 bg-surface-subtle text-muted-foreground")}>{starter.label}</span>
                    <ArrowRight aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
