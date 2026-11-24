'use client'

import * as React from "react"
import { cn } from "@/lib/utils"

interface FilterOption {
  label: string
  value: string
}

interface FilterGroupProps {
  options: FilterOption[]
  value: string
  onChange: (value: string) => void
  className?: string
}

export function FilterGroup({ options, value, onChange, className }: FilterGroupProps) {
  return (
    <div className={cn("inline-flex flex-wrap gap-1 rounded-lg border border-border/70 bg-surface-subtle p-1", className)}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            value === option.value
              ? "bg-card text-foreground shadow-xs"
              : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
