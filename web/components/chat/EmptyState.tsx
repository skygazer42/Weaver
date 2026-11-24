'use client'

import React from 'react'
import Image from 'next/image'
import { ArrowRight, Sparkles, TrendingUp, Code2, BookOpen } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'

interface EmptyStateProps {
  onStarterClick?: (text: string, mode: string) => void
}

export function EmptyState({ onStarterClick }: EmptyStateProps) {
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
        <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl border border-border/50 bg-white shadow-surface">
          <Image src="/logo.png" alt="Weaver" width={52} height={52} priority className="object-contain" />
        </div>
        
        <div className="max-w-2xl space-y-2">
            <h2 className="text-balance text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                {t('emptyStateTitle')}
            </h2>
            <p className="text-balance text-sm leading-6 text-muted-foreground sm:text-base">
                {t('emptyStateSubtitle')}
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
            className="group flex h-full flex-col justify-between gap-4 rounded-xl border border-border/60 bg-card/85 p-4 text-left transition-[background-color,border-color,box-shadow] hover:border-border hover:bg-card hover:shadow-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-2"
          >
            <div className="flex items-start gap-3">
              <div className="shrink-0 rounded-lg bg-surface-subtle p-2 text-muted-foreground transition-colors group-hover:text-primary">
                <starter.icon className="h-4 w-4" />
              </div>
              <p className="min-w-0 flex-1 text-sm font-medium leading-6 text-foreground">
                {starter.text}
              </p>
            </div>
            <div className="flex items-center justify-between gap-2 pl-11">
              <span className="rounded-full bg-surface-subtle px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">{starter.label}</span>
              <ArrowRight aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5 motion-reduce:transform-none" />
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
