'use client'

import React from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface CitationBadgeProps {
  num: string
}

export function CitationBadge({ num }: CitationBadgeProps) {
  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <button type="button" aria-label={`Source ${num}`} className="ml-0.5 inline-flex -translate-y-0.5 items-center rounded bg-primary/10 px-1.5 py-0.5 align-super text-[11px] font-medium leading-none tabular-nums text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 [html:not(.dark)_.prose-on-primary_&]:bg-primary-foreground/15 [html:not(.dark)_.prose-on-primary_&]:text-primary-foreground [html:not(.dark)_.prose-on-primary_&]:hover:bg-primary-foreground/25">
            [{num}]
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-[300px] break-words rounded-lg border border-border/80 bg-popover px-3 py-2 text-popover-foreground shadow-elevated">
          <div className="space-y-1">
            <p className="text-xs font-medium tabular-nums">Source [{num}]</p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
