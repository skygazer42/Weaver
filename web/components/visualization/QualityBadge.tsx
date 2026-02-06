'use client'

import { cn } from '@/lib/utils'

interface QualityBadgeProps {
  label: string
  value: number
  className?: string
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function scoreClasses(value: number): string {
  if (value >= 0.8) {
    return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
  }
  if (value >= 0.6) {
    return 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300'
  }
  return 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300'
}

export function QualityBadge({ label, value, className }: QualityBadgeProps) {
  const normalized = clamp(value)
  const percent = Math.round(normalized * 100)

  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 rounded-md border px-2 py-1 text-xs font-medium',
        scoreClasses(normalized),
        className,
      )}
    >
      <span className="uppercase tracking-wide opacity-80">{label}</span>
      <span>{percent}%</span>
    </div>
  )
}
