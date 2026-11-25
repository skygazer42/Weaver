'use client'

import React from 'react'
import Image from 'next/image'
import logo from '@/public/logo.png'
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
    <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col items-center justify-center px-4 py-6 sm:px-6 sm:py-8">
      
      {/* Hero Section */}
      <div className="mb-5 flex flex-col items-center gap-2 text-center sm:mb-8">
        <div className="flex items-center gap-3 sm:flex-col sm:gap-4">
          <Image src={logo} alt="Weaver" width={56} height={56} priority className="h-10 w-10 object-contain sm:h-14 sm:w-14" />
          <h2 className="text-balance text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            {t('emptyStateTitle')}
          </h2>
        </div>
        <p className="max-w-2xl text-balance text-sm leading-6 text-muted-foreground sm:text-base">
          {t('emptyStateSubtitle')}
        </p>
      </div>

      {/* Starter Grid */}
      <div className="grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2 sm:gap-3">
        {starters.map((starter, i) => (
          <button
            key={i}
            type="button"
            onClick={() => {
                if (onStarterClick) {
                    onStarterClick(starter.text, starter.mode)
                }
            }}
            className="group grid grid-cols-[1.75rem_minmax(0,1fr)_1rem] items-start gap-2.5 rounded-xl border border-border/60 bg-card/85 p-3 text-left transition-[background-color,border-color,box-shadow] hover:border-border hover:bg-card hover:shadow-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-2 sm:grid-cols-[2rem_minmax(0,1fr)_1rem] sm:gap-3 sm:p-4"
          >
            <div className="rounded-lg bg-surface-subtle p-1.5 text-muted-foreground transition-colors group-hover:text-primary sm:p-2">
              <starter.icon aria-hidden="true" className="h-4 w-4" />
            </div>
            <div className="flex min-w-0 flex-col items-start gap-1.5 sm:gap-2">
              <p className="text-sm font-medium leading-5 text-foreground sm:leading-6">
                {starter.text}
              </p>
              <span className="rounded-md bg-surface-subtle px-2 py-0.5 text-xs font-medium leading-4 text-muted-foreground">{starter.label}</span>
            </div>
            <ArrowRight aria-hidden="true" className="h-4 w-4 self-center text-muted-foreground/60 transition-transform group-hover:translate-x-0.5 motion-reduce:transform-none" />
          </button>
        ))}
      </div>
    </div>
  )
}
