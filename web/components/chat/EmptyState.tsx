'use client'

import Image from 'next/image'
import { ArrowRight, Sparkles, TrendingUp, Code2, BookOpen } from '@/components/ui/icons'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { deriveUiModeId, searchModeFromId, type CoreModeId, type SearchMode } from '@/lib/chat-mode'

interface EmptyStateProps {
  selectedMode: SearchMode
  mcpMode: boolean
  onModeSelect: (mode: SearchMode) => void
  onStarterClick?: (text: string, mode: CoreModeId) => void
}

const MODE_COLORS: Record<string, { icon: string; activeIcon: string; activeRing: string }> = {
  ultra: {
    icon: 'text-violet-600 dark:text-violet-400',
    activeIcon: 'text-violet-700 dark:text-violet-300',
    activeRing: 'ring-violet-500/20',
  },
  agent: {
    icon: 'text-sky-600 dark:text-sky-400',
    activeIcon: 'text-sky-700 dark:text-sky-300',
    activeRing: 'ring-sky-500/20',
  },
  web: {
    icon: 'text-emerald-600 dark:text-emerald-400',
    activeIcon: 'text-emerald-700 dark:text-emerald-300',
    activeRing: 'ring-emerald-500/20',
  },
  direct: {
    icon: 'text-amber-600 dark:text-amber-400',
    activeIcon: 'text-amber-700 dark:text-amber-300',
    activeRing: 'ring-amber-500/20',
  },
}

export function EmptyState({ selectedMode, mcpMode, onModeSelect, onStarterClick }: EmptyStateProps) {
  const { t } = useI18n()

  const activeMode = deriveUiModeId(selectedMode, mcpMode)

  const starters = [
    {
      icon: TrendingUp,
      text: t('starterAnalyze'),
      mode: "ultra" as CoreModeId
    },
    {
      icon: Code2,
      text: t('starterWrite'),
      mode: "agent" as CoreModeId
    },
    {
      icon: BookOpen,
      text: t('starterSummarize'),
      mode: "web" as CoreModeId
    },
    {
      icon: Sparkles,
      text: t('starterPlan'),
      mode: "direct" as CoreModeId
    }
  ]

  return (
    <div className="flex flex-col items-center justify-center h-full w-full max-w-[820px] mx-auto p-6 animate-fade-in">

      {/* Hero Section */}
      <div className="flex flex-col items-center space-y-5 mb-14 text-center">
        <div className="flex size-18 items-center justify-center rounded-2xl bg-background shadow-[0_12px_36px_rgba(0,0,0,0.08)] overflow-hidden">
          <Image
            src="/logo.png"
            alt="Weaver"
            width={56}
            height={56}
            className="h-14 w-14 object-contain"
            priority
          />
        </div>

        <div className="space-y-3 max-w-md">
          <h2 className="text-2xl font-semibold text-foreground text-balance tracking-tight">
            {t('emptyStateTitle')}
          </h2>
          <p className="text-stone-500 dark:text-stone-400 text-base text-pretty leading-relaxed">
            {t('emptyStateSubtitle')} <br className="hidden sm:block" />
            {t('emptyStateDescription')}
          </p>
        </div>
      </div>

      {/* Starter Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-[680px]">
        {starters.map((starter, i) => {
          const isActive = activeMode === starter.mode
          const colors = (MODE_COLORS[starter.mode] ?? MODE_COLORS['direct'])!
          return (
            <button
              key={i}
              onClick={() => {
                onModeSelect(searchModeFromId(starter.mode))
                onStarterClick?.(starter.text, starter.mode)
              }}
              className={cn(
                "group flex items-start gap-3.5 p-4 rounded-xl text-left transition-all duration-200",
                "bg-background shadow-[0_8px_30px_rgba(0,0,0,0.04)] hover:shadow-[0_12px_36px_rgba(0,0,0,0.06)] hover:-translate-y-0.5",
                isActive
                  ? ["ring-1", colors.activeRing]
                  : "ring-1 ring-border/10"
              )}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className={cn(
                "p-2.5 rounded-lg transition-colors",
                isActive
                  ? ["bg-muted/30", colors.activeIcon]
                  : ["bg-muted/20", colors.icon, "group-hover:bg-muted/40"]
              )}>
                <starter.icon className="h-5 w-5" />
              </div>
              <div className="flex-1 space-y-1.5 min-w-0">
                <p className="text-sm font-medium leading-snug group-hover:text-foreground transition-colors">
                  {starter.text}
                </p>
                <div className={cn(
                  "flex items-center gap-1 text-xs font-medium text-muted-foreground"
                )}>
                  <span>{t('useMode')} {starter.mode} {t('mode')}</span>
                  <ArrowRight className="h-2.5 w-2.5" />
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
