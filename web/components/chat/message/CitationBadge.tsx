'use client'

import React from 'react'
import { Tooltip, TooltipContent, TooltipPortal, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useI18n } from '@/lib/i18n/i18n-context'
import { parseStudioSourceUrl, type StudioSource } from '@/lib/researchStudio'
import type { MessageSource } from '@/types/chat'

interface CitationBadgeProps {
  num: string
  sources?: readonly (StudioSource | MessageSource)[]
  onCitationClick?: (sourceIndex: number) => void
}

export function CitationBadge({ num, sources, onCitationClick }: CitationBadgeProps) {
  const { t } = useI18n()
  const index = Number(num)
  const match = sources?.find((source, i) => ('index' in source ? source.index : i + 1) === index)
  const url = parseStudioSourceUrl(match?.url)
  const domain = url?.hostname.replace(/^www\./, '')
  const label = t('studioCitation').replace('{count}', num)
  const title = (url && match?.title) || label
  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <button type="button" aria-label={label} onClick={onCitationClick ? () => onCitationClick(index) : undefined} className="ml-0.5 inline-flex -translate-y-0.5 items-center rounded bg-primary/10 px-1.5 py-0.5 align-super text-[11px] font-medium leading-none tabular-nums text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 [html:not(.dark)_.prose-on-primary_&]:bg-primary-foreground/15 [html:not(.dark)_.prose-on-primary_&]:text-primary-foreground [html:not(.dark)_.prose-on-primary_&]:hover:bg-primary-foreground/25">
            [{num}]
          </button>
        </TooltipTrigger>
        <TooltipPortal>
          <TooltipContent className="max-w-[300px] space-y-1 break-words rounded-lg border border-border/80 bg-popover px-3 py-2 text-popover-foreground shadow-elevated">
            <p className="text-xs font-semibold leading-5">{title}</p>
            {domain && <p className="text-xs text-muted-foreground">{domain}</p>}
          </TooltipContent>
        </TooltipPortal>
      </Tooltip>
    </TooltipProvider>
  )
}
