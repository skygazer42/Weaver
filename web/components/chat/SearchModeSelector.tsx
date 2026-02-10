'use client'

import React from 'react'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Settings2, Search, Bot, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useI18n } from '@/lib/i18n/i18n-context'

export interface SearchMode {
  useWebSearch: boolean
  useAgent: boolean
  useDeepSearch: boolean
}

interface SearchModeSelectorProps {
  mode: SearchMode
  onChange: (mode: SearchMode) => void
}

export function SearchModeSelector({ mode, onChange }: SearchModeSelectorProps) {
  const { t } = useI18n()

  const updateMode = (key: keyof SearchMode, value: boolean) => {
    onChange({ ...mode, [key]: value })
  }

  const activeCount = [mode.useWebSearch, mode.useAgent, mode.useDeepSearch].filter(Boolean).length

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "gap-2",
            activeCount > 0 && "border-primary text-primary"
          )}
        >
          <Settings2 className="h-4 w-4" />
          <span className="hidden sm:inline">{t('searchMode')}</span>
          {activeCount > 0 && (
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
              {activeCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="start">
        <div className="space-y-4">
          <div className="space-y-2">
            <h4 className="font-medium leading-none">{t('searchModeSettings')}</h4>
            <p className="text-sm text-muted-foreground">
              {t('searchModeSubtitle')}
            </p>
          </div>

          <div className="space-y-4">
            {/* Web Search */}
            <div className="flex items-center justify-between space-x-2">
              <div className="flex items-center space-x-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10">
                  <Search className="h-5 w-5 text-blue-500" />
                </div>
                <div className="space-y-0.5">
                  <Label htmlFor="web-search" className="cursor-pointer">
                    {t('webSearch')}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t('webSearchDesc')}
                  </p>
                </div>
              </div>
              <Switch
                id="web-search"
                checked={mode.useWebSearch}
                onCheckedChange={(checked) => updateMode('useWebSearch', checked)}
              />
            </div>

            {/* Agent Mode */}
            <div className="flex items-center justify-between space-x-2">
              <div className="flex items-center space-x-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10">
                  <Bot className="h-5 w-5 text-purple-500" />
                </div>
                <div className="space-y-0.5">
                  <Label htmlFor="agent" className="cursor-pointer">
                    {t('agentMode')}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t('agentModeDesc')}
                  </p>
                </div>
              </div>
              <Switch
                id="agent"
                checked={mode.useAgent}
                onCheckedChange={(checked) => updateMode('useAgent', checked)}
              />
            </div>

            {/* Deep Search */}
            <div className="flex items-center justify-between space-x-2">
              <div className="flex items-center space-x-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10">
                  <Sparkles className="h-5 w-5 text-amber-500" />
                </div>
                <div className="space-y-0.5">
                  <Label htmlFor="deep-search" className="cursor-pointer">
                    {t('deepSearchLabel')}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t('deepSearchDesc')}
                  </p>
                </div>
              </div>
              <Switch
                id="deep-search"
                checked={mode.useDeepSearch}
                onCheckedChange={(checked) => updateMode('useDeepSearch', checked)}
                disabled={!mode.useAgent}
              />
            </div>
          </div>

          {mode.useDeepSearch && !mode.useAgent && (
            <div className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-600">
              {t('deepSearchRequiresAgent')}
            </div>
          )}

          <div className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">
            <strong>{t('tipLabel')}</strong>
            <ul className="mt-1 ml-4 list-disc space-y-1">
              <li>{t('tipOnlyWeb')}</li>
              <li>{t('tipAgent')}</li>
              <li>{t('tipDeep')}</li>
            </ul>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
