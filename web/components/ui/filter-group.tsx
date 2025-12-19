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
    <div className={cn("flex flex-wrap gap-2", className)}>
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "px-3 py-1.5 text-sm font-medium rounded-full border transition-all",
            value === option.value
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-background text-muted-foreground hover:border-foreground/20 hover:text-foreground"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
