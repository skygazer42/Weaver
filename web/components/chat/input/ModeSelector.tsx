'use client'

import React, { useState, useCallback } from 'react'
import { Globe, Bot, Rocket, Plug, ChevronDown, Check } from '@/components/ui/icons'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { deriveUiModeId, searchModeFromId, type SearchMode } from '@/lib/chat-mode'
import type { McpProviderId } from '@/hooks/useChatState'

interface ModeSelectorProps {
  searchMode: SearchMode
  onSearchModeChange: (mode: SearchMode) => void
  mcpMode: boolean
  onMcpModeChange: (enabled: boolean) => void
  mcpProvider: McpProviderId
  onMcpProviderChange: (provider: McpProviderId) => void
}

interface ModeOption {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  color: string
  activeColor: string
  activeBg: string
}

interface McpOption {
  id: McpProviderId
  label: string
}

const MODE_STYLES: Record<string, { color: string; activeColor: string; activeBg: string }> = {
  web: {
    color: 'text-emerald-500/70 dark:text-emerald-400/70',
    activeColor: 'text-emerald-600 dark:text-emerald-400',
    activeBg: 'bg-emerald-500/10 dark:bg-emerald-500/15 border-emerald-500/20',
  },
  agent: {
    color: 'text-sky-500/70 dark:text-sky-400/70',
    activeColor: 'text-sky-600 dark:text-sky-400',
    activeBg: 'bg-sky-500/10 dark:bg-sky-500/15 border-sky-500/20',
  },
  ultra: {
    color: 'text-violet-500/70 dark:text-violet-400/70',
    activeColor: 'text-violet-600 dark:text-violet-400',
    activeBg: 'bg-violet-500/10 dark:bg-violet-500/15 border-violet-500/20',
  },
  mcp: {
    color: 'text-amber-500/70 dark:text-amber-400/70',
    activeColor: 'text-amber-600 dark:text-amber-400',
    activeBg: 'bg-amber-500/10 dark:bg-amber-500/15 border-amber-500/20',
  },
}

export function ModeSelector({
  searchMode,
  onSearchModeChange,
  mcpMode,
  onMcpModeChange,
  mcpProvider,
  onMcpProviderChange,
}: ModeSelectorProps) {
  const { t } = useI18n()
  const [isMcpOpen, setIsMcpOpen] = useState(false)

  const activeMode = deriveUiModeId(searchMode, mcpMode)

  const modes: ModeOption[] = [
    { id: 'web', label: t('web'), icon: Globe, ...MODE_STYLES['web']! },
    { id: 'agent', label: t('agent'), icon: Bot, ...MODE_STYLES['agent']! },
    { id: 'ultra', label: t('ultra'), icon: Rocket, ...MODE_STYLES['ultra']! },
  ]

  const mcpOptions: McpOption[] = [
    { id: 'filesystem', label: t('filesystem') },
    { id: 'memory', label: t('memory') },
  ]

  const handleModeClick = useCallback((modeId: string) => {
    if (activeMode === modeId) onSearchModeChange(searchModeFromId('direct'))
    else if (modeId === 'web') onSearchModeChange(searchModeFromId('web'))
    else if (modeId === 'agent') onSearchModeChange(searchModeFromId('agent'))
    else if (modeId === 'ultra') onSearchModeChange(searchModeFromId('ultra'))
    onMcpModeChange(false)
    setIsMcpOpen(false)
  }, [activeMode, onMcpModeChange, onSearchModeChange])

  const handleMcpToggle = useCallback(() => {
    if (mcpMode) {
      onMcpModeChange(false)
      onSearchModeChange(searchModeFromId('direct'))
      setIsMcpOpen(false)
    } else {
      onMcpModeChange(true)
      onSearchModeChange(searchModeFromId('agent'))
      setIsMcpOpen((prev) => !prev)
    }
  }, [mcpMode, onMcpModeChange, onSearchModeChange])

  const handleMcpSelect = useCallback((next: McpProviderId) => {
    onMcpProviderChange(next)
    onMcpModeChange(true)
    onSearchModeChange(searchModeFromId('agent'))
    setIsMcpOpen(false)
  }, [onMcpModeChange, onMcpProviderChange, onSearchModeChange])

  const mcpStyle = MODE_STYLES['mcp']!

  return (
    <div className="flex items-center gap-1 self-start ml-1 mb-1 p-0.5 rounded-xl bg-muted/20 border border-border/20" role="radiogroup" aria-label="Search mode">
      {modes.map((mode) => {
        const Icon = mode.icon
        const isActive = activeMode === mode.id
        return (
          <button
            key={mode.id}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => handleModeClick(mode.id)}
            className={cn(
              "relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 border border-transparent",
              isActive
                ? [mode.activeBg, "text-foreground shadow-sm"]
                : "text-muted-foreground hover:text-foreground hover:bg-card/50"
            )}
          >
            <Icon className={cn("h-3.5 w-3.5 transition-colors", isActive ? mode.activeColor : mode.color)} />
            {mode.label}
          </button>
        )
      })}

      {/* MCP Dropdown */}
      <div className="relative">
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={isMcpOpen}
          onClick={handleMcpToggle}
          className={cn(
            "relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 border border-transparent",
            mcpMode
              ? [mcpStyle.activeBg, "text-foreground shadow-sm"]
              : "text-muted-foreground hover:text-foreground hover:bg-card/50"
          )}
        >
          <Plug className={cn("h-3.5 w-3.5 transition-colors", mcpMode ? mcpStyle.activeColor : mcpStyle.color)} />
          {mcpMode ? (mcpOptions.find(o => o.id === mcpProvider)?.label || 'MCP') : 'MCP'}
          <ChevronDown className="h-3 w-3 opacity-60" />
        </button>

        {isMcpOpen && (
          <div
            role="listbox"
            aria-label="MCP providers"
            className="absolute bottom-full left-0 mb-2 w-40 bg-popover/90 backdrop-blur-xl border border-border/30 rounded-xl shadow-lg z-50 overflow-hidden animate-scale-in"
          >
            <div className="p-1">
              {mcpOptions.map(opt => (
                <button
                  key={opt.id}
                  role="option"
                  aria-selected={mcpProvider === opt.id && mcpMode}
                  onClick={() => handleMcpSelect(opt.id)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2 py-2 text-xs transition-colors hover:bg-muted",
                    mcpProvider === opt.id && mcpMode && "bg-amber-500/10 font-medium text-amber-600 dark:text-amber-400"
                  )}
                >
                  {opt.label}
                  {mcpProvider === opt.id && mcpMode && <Check className="h-3 w-3 text-amber-500" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
