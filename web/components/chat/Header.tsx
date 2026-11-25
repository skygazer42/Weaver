'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { PanelLeft, Sun, Moon, ChevronDown, Check, FileSpreadsheet, LayoutPanelLeft, Settings, Monitor, SquarePen } from 'lucide-react'
import { useTheme } from '@/components/theme-provider'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { usePublicModels } from '@/hooks/usePublicModels'
import { getModelProviders } from '@/lib/models'
import type { Workspace } from '@/lib/workspace'

interface HeaderProps {
  project?: Pick<Workspace, 'id' | 'name'>
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onNewChat?: () => void
  selectedModel: string
  onModelChange: (model: string) => void
  onOpenSettings: () => void
  onToggleArtifacts?: () => void
  hasArtifacts?: boolean
  isInitializing?: boolean
  showBrowserToggle?: boolean
  isBrowserOpen?: boolean
  onToggleBrowser?: () => void
}

export function Header({ project, sidebarOpen, onToggleSidebar, onNewChat, selectedModel, onModelChange, onOpenSettings, onToggleArtifacts, hasArtifacts, isInitializing, showBrowserToggle, isBrowserOpen, onToggleBrowser }: HeaderProps) {
  const { setTheme } = useTheme()
  const { t } = useI18n()
  const { models: publicModels } = usePublicModels()
  const [isModelOpen, setIsModelOpen] = useState(false)
  const [modelQuery, setModelQuery] = useState('')

  const allowlistKey = publicModels?.options?.length ? publicModels.options.join('|') : ''
  const allowlist = publicModels?.options?.length ? new Set(publicModels.options) : null
  const modelProviders = getModelProviders(publicModels?.options)
  const models = modelProviders.flatMap(provider => provider.models)
  const currentModelName = models.find(model => model.id === selectedModel)?.name || selectedModel
  const query = modelQuery.trim().toLowerCase()
  const filteredProviders = modelProviders.map(provider => ({
    ...provider,
    models: provider.models.filter(model => `${provider.name} ${model.name} ${model.id}`.toLowerCase().includes(query)),
  })).filter(provider => provider.models.length > 0)

  const handleModelOpenChange = (open: boolean) => {
    setIsModelOpen(open)
    if (!open) setModelQuery('')
  }

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
          aria-label={sidebarOpen ? t('collapseSidebar') : t('expandSidebar')}
          title={sidebarOpen ? t('collapseSidebar') : t('expandSidebar')}
          className={cn('shrink-0 text-muted-foreground hover:text-foreground', sidebarOpen && 'md:hidden')}
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
        {!sidebarOpen && onNewChat && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onNewChat}
            aria-label={t('newChat')}
            title={t('newChat')}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <SquarePen className="h-4 w-4" />
          </Button>
        )}
        <Button variant="ghost" size="sm" className="min-w-0 text-sm" asChild>
          <Link
            href={project ? `/workspace?workspace_id=${encodeURIComponent(project.id)}` : '/workspace'}
            aria-label={project ? `Back to project ${project.name}` : undefined}
            className="min-w-0 gap-2 px-2"
          >
            <FileSpreadsheet className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <span className="truncate">{project?.name ?? t('workbench')}</span>
          </Link>
        </Button>
      </div>

      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {hasArtifacts && (
          <Button type="button" variant="ghost" size="icon" onClick={onToggleArtifacts} aria-label="Open artifacts" className="text-muted-foreground xl:hidden">
            <LayoutPanelLeft className="h-4 w-4" />
          </Button>
        )}
        <Popover open={isModelOpen} onOpenChange={handleModelOpenChange}>
          <PopoverTrigger asChild>
            <button
              type="button"
              disabled={isInitializing}
              title={selectedModel}
              className="flex h-8 max-w-[140px] items-center gap-2 rounded-md border border-border bg-card px-2.5 text-xs font-medium shadow-xs transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-2 sm:max-w-[240px] sm:text-sm"
            >
              <span className="truncate">
                {currentModelName.includes('/') ? currentModelName.slice(currentModelName.lastIndexOf('/') + 1) : currentModelName}
              </span>
              <ChevronDown className={cn('h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform', isModelOpen && 'rotate-180')} />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="flex max-h-[var(--radix-popover-content-available-height)] w-72 max-w-[calc(100vw-2rem)] flex-col overflow-hidden p-1.5" aria-label="Select model">
            {models.length > 8 && (
              <div className="sticky top-0 z-10 shrink-0 bg-popover pb-1.5">
                <Input value={modelQuery} onChange={event => setModelQuery(event.target.value)} placeholder={t('filterModels')} aria-label="Filter models" className="h-8 text-xs" />
              </div>
            )}
            <div className="min-h-0 max-h-80 overflow-y-auto">
              {filteredProviders.map(provider => (
                <div key={provider.id} className="pb-1 last:pb-0">
                  <div className="px-2.5 pb-1 pt-2 text-[11px] font-semibold tracking-wide text-muted-foreground">{provider.name}</div>
                  {provider.models.map(model => (
                    <button
                      key={model.id}
                      type="button"
                      aria-pressed={selectedModel === model.id}
                      onClick={() => {
                        onModelChange(model.id)
                        handleModelOpenChange(false)
                      }}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset',
                        selectedModel === model.id && 'bg-primary/10 font-medium text-primary'
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate" title={model.id}>{model.name}</span>
                      {model.isPro && <Badge variant="subtle">Pro</Badge>}
                      {model.isVision && <Badge variant="subtle">Vision</Badge>}
                      {selectedModel === model.id && <Check aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />}
                    </button>
                  ))}
                </div>
              ))}
              {filteredProviders.length === 0 && <p role="status" className="px-2.5 py-4 text-center text-xs text-muted-foreground">{t('noModelsFound')}</p>}
            </div>
          </PopoverContent>
        </Popover>
        {showBrowserToggle && (
          <Button type="button" variant="ghost" size="icon" onClick={onToggleBrowser} aria-pressed={isBrowserOpen} aria-label={isBrowserOpen ? t('hideBrowser') : t('showBrowser')} title={isBrowserOpen ? t('hideBrowser') : t('showBrowser')} className={cn('shrink-0 text-muted-foreground hover:text-foreground', isBrowserOpen && 'bg-primary/10 text-primary')}>
            <Monitor className="h-4 w-4" />
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          disabled={isInitializing}
          onClick={() => setTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark')}
          aria-label={t('toggleTheme')}
          title={t('toggleTheme')}
          className="relative shrink-0 text-muted-foreground hover:text-foreground"
        >
          <Sun className="h-4 w-4 dark:hidden" />
          <Moon className="hidden h-4 w-4 dark:block" />
        </Button>
        <Button type="button" variant="ghost" size="icon" disabled={isInitializing} onClick={onOpenSettings} aria-label={t('settings')} title={t('settings')} className="shrink-0 text-muted-foreground hover:text-foreground">
          <Settings className="h-4 w-4" />
        </Button>
      </div>
    </header>
  )
}
