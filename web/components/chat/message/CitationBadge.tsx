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
          <sup className="ml-0.5 cursor-pointer text-[10px] font-bold text-primary hover:underline decoration-dotted select-none bg-primary/10 px-1 rounded-sm">
            [{num}]
          </sup>
        </TooltipTrigger>
        <TooltipContent className="max-w-[300px] break-words">
          <div className="space-y-1">
            <p className="font-semibold text-xs">Source [{num}]</p>
            <p className="text-xs text-muted-foreground">Reference details would appear here.</p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
