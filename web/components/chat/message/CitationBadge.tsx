'use client'

import React from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface CitationBadgeProps {
  num: string
  active?: boolean
  onClick?: (num: string) => void
}

export function CitationBadge({ num, active = false, onClick }: CitationBadgeProps) {
  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <sup
            role="button"
            tabIndex={0}
            onClick={() => onClick?.(num)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick?.(num)
              }
            }}
            className={[
              'ml-0.5 cursor-pointer text-[10px] font-bold hover:underline decoration-dotted select-none px-1 rounded-sm',
              active ? 'bg-primary text-primary-foreground' : 'text-primary bg-primary/10',
            ].join(' ')}
          >
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
