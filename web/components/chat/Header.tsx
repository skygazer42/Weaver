'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import { PanelLeft, Sun, Moon, ChevronDown, Check, FileSpreadsheet, LayoutPanelLeft, Settings } from 'lucide-react'
import { useTheme } from '@/components/theme-provider'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { usePublicModels } from '@/hooks/usePublicModels'
import type { Workspace } from '@/lib/workspace'

interface HeaderProps {
  project?: Pick<Workspace, 'id' | 'name'>
  sidebarOpen: boolean
  onToggleSidebar: () => void
  selectedModel: string
  onModelChange: (model: string) => void
  onOpenSettings: () => void
  onToggleArtifacts?: () => void
  hasArtifacts?: boolean
}

export function Header({ project, sidebarOpen, onToggleSidebar, selectedModel, onModelChange, onOpenSettings, onToggleArtifacts, hasArtifacts }: HeaderProps) {
  const { setTheme } = useTheme()
  const { t } = useI18n()
  const { models: publicModels } = usePublicModels()
  const [isModelOpen, setIsModelOpen] = useState(false)

  const staticModels = [
    { id: 'gpt-5', name: 'GPT-5', provider: 'OpenAI' },
    { id: 'gpt-4.1', name: 'GPT-4.1', provider: 'OpenAI' },
    { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' },
    { id: 'claude-sonnet-4-5-20250514', name: 'Claude Sonnet 4.5', provider: 'Anthropic' },
    { id: 'claude-opus-4-20250514', name: 'Claude Opus 4', provider: 'Anthropic' },
    { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4', provider: 'Anthropic' },
    { id: 'deepseek-chat', name: 'deepseek-chat', provider: t('deepseek') },
    { id: 'deepseek-reasoner', name: 'deepseek-reasoner', provider: t('deepseek') },
    { id: 'qwen-plus', name: 'qwen-plus', provider: t('qwen') },
    { id: 'qwen3-vl-flash', name: 'qwen3-vl-flash', provider: t('qwen') },
    { id: 'glm-4.6', name: 'GLM-4.6', provider: t('zhipu') },
    { id: 'glm-4.6v', name: 'glm-4.6v', provider: t('zhipu') },
  ]

  const allowlistKey = publicModels?.options?.length ? publicModels.options.join('|') : ''
  const allowlist = publicModels?.options?.length ? new Set(publicModels.options) : null
  const models = allowlist
    ? [
        ...staticModels.filter((model) => allowlist.has(model.id)),
        ...publicModels!.options
          .filter((id) => !staticModels.some((model) => model.id === id))
          .map((id) => ({ id, name: id, provider: 'Custom' })),
      ]
    : staticModels
  const currentModelName = models.find(model => model.id === selectedModel)?.name || selectedModel
  const providers = Array.from(new Set(models.map(model => model.provider)))

  // Keep saved choices within the backend's supported model list.
  useEffect(() => {
    if (!allowlist || models.length === 0 || allowlist.has(selectedModel)) return
    const next =
      (publicModels?.default && allowlist.has(publicModels.default) && publicModels.default) ||
      models[0]!.id
    onModelChange(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowlistKey])

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border/80 bg-background/90 px-3 backdrop-blur-md sm:px-5">
      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          className={cn('shrink-0 text-muted-foreground', sidebarOpen && 'md:hidden')}
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" className="min-w-0 text-sm" asChild>
          <Link
            href={project ? `/workspace?workspace_id=${encodeURIComponent(project.id)}` : '/workspace'}
            aria-label={project ? `Back to project ${project.name}` : undefined}
            className="min-w-0 gap-2 px-2"
          >
            <FileSpreadsheet className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <span className="truncate">{project?.name ?? 'Workbench'}</span>
          </Link>
        </Button>
      </div>

      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {hasArtifacts && (
          <Button type="button" variant="ghost" size="icon" onClick={onToggleArtifacts} aria-label="Open artifacts" className="text-muted-foreground xl:hidden">
            <LayoutPanelLeft className="h-4 w-4" />
          </Button>
        )}
        <Popover open={isModelOpen} onOpenChange={setIsModelOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              title={currentModelName}
              className="flex h-8 max-w-[140px] items-center gap-2 rounded-md border border-border bg-card px-2.5 text-xs font-medium shadow-xs transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-2 sm:max-w-[240px] sm:text-sm"
            >
              <span className="truncate">
                {currentModelName.includes('/') ? currentModelName.slice(currentModelName.lastIndexOf('/') + 1) : currentModelName}
              </span>
              <ChevronDown className={cn('h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform', isModelOpen && 'rotate-180')} />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="max-h-[var(--radix-popover-content-available-height)] w-72 max-w-[calc(100vw-2rem)] overflow-y-auto p-1.5" aria-label="Select model">
            {providers.map(provider => (
              <div key={provider} className="pb-1 last:pb-0">
                <div className="px-2.5 pb-1 pt-2 text-[11px] font-semibold tracking-wide text-muted-foreground">{provider}</div>
                {models.filter(model => model.provider === provider).map(model => (
                  <button
                    key={model.id}
                    type="button"
                    aria-pressed={selectedModel === model.id}
                    onClick={() => {
                      onModelChange(model.id)
                      setIsModelOpen(false)
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset',
                      selectedModel === model.id && 'bg-primary/10 font-medium text-primary'
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate" title={model.name}>{model.name}</span>
                    {['qwen3-vl-flash', 'glm-4.6v'].includes(model.id) && <Badge variant="subtle">Vision</Badge>}
                    {selectedModel === model.id && <Check aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />}
                  </button>
                ))}
              </div>
            ))}
          </PopoverContent>
        </Popover>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => setTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark')}
          aria-label="Toggle theme"
          className="relative shrink-0 text-muted-foreground hover:text-foreground"
        >
          <Sun className="h-4 w-4 dark:hidden" />
          <Moon className="hidden h-4 w-4 dark:block" />
        </Button>
        <Button type="button" variant="ghost" size="icon" onClick={onOpenSettings} aria-label="Settings" className="shrink-0 text-muted-foreground hover:text-foreground">
          <Settings className="h-4 w-4" />
        </Button>
      </div>
    </header>
  )
}
