'use client'

import React, { useState, useCallback } from 'react'
import { Globe, Bot, Rocket, Plug, ChevronDown, Check } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'

interface ModeSelectorProps {
  searchMode: string
  onModeChange: (mode: string) => void
}

interface ModeOption {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  color: string
  bg: string
  border: string
}

interface McpOption {
  id: string
  label: string
}

export function ModeSelector({ searchMode, onModeChange }: ModeSelectorProps) {
  const { t } = useI18n()
  const [isMcpOpen, setIsMcpOpen] = useState(false)
  const [selectedMcp, setSelectedMcp] = useState('filesystem')

  const modes: ModeOption[] = [
    { id: 'web', label: t('web'), icon: Globe, color: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
    { id: 'agent', label: t('agent'), icon: Bot, color: 'text-purple-500', bg: 'bg-purple-500/10', border: 'border-purple-500/20' },
    { id: 'ultra', label: t('ultra'), icon: Rocket, color: 'text-indigo-500', bg: 'bg-indigo-500/10', border: 'border-indigo-500/20' },
  ]

  const mcpOptions: McpOption[] = [
    { id: 'filesystem', label: t('filesystem') },
    { id: 'github', label: t('github') },
    { id: 'brave', label: t('braveSearch') },
    { id: 'memory', label: t('memory') },
  ]

  const handleModeClick = useCallback((modeId: string) => {
    if (searchMode === modeId) {
      onModeChange('')
    } else {
      onModeChange(modeId)
    }
    setIsMcpOpen(false)
  }, [searchMode, onModeChange])

  const handleMcpToggle = useCallback(() => {
    if (searchMode === 'mcp') {
      onModeChange('')
      setIsMcpOpen(false)
    } else {
      onModeChange('mcp')
      setIsMcpOpen(!isMcpOpen)
    }
  }, [searchMode, onModeChange, isMcpOpen])

  const handleMcpSelect = useCallback((mcpId: string) => {
    setSelectedMcp(mcpId)
    onModeChange('mcp')
    setIsMcpOpen(false)
  }, [onModeChange])

  return (
    <div className="flex items-center gap-1 self-start ml-1 mb-1" role="radiogroup" aria-label="Search mode">
      {modes.map((mode) => {
        const Icon = mode.icon
        const isActive = searchMode === mode.id
        return (
          <button
            key={mode.id}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => handleModeClick(mode.id)}
            className={cn(
              "relative flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 border",
              isActive
                ? cn("text-foreground shadow-sm", mode.bg, mode.border)
                : "text-muted-foreground border-transparent hover:bg-muted/50"
            )}
          >
            <Icon className={cn("h-3.5 w-3.5 transition-colors", isActive ? mode.color : "text-muted-foreground")} />
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
            "relative flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 border",
            searchMode === 'mcp'
              ? "bg-pink-500/10 text-foreground border-pink-500/20 shadow-sm"
              : "text-muted-foreground border-transparent hover:bg-muted/50"
          )}
        >
          <Plug className={cn("h-3.5 w-3.5 transition-colors", searchMode === 'mcp' ? "text-pink-500" : "text-muted-foreground")} />
          {searchMode === 'mcp' ? (mcpOptions.find(o => o.id === selectedMcp)?.label || 'MCP') : 'MCP'}
          <ChevronDown className="h-3 w-3 opacity-50" />
        </button>

        {isMcpOpen && (
          <div
            role="listbox"
            aria-label="MCP providers"
            className="absolute bottom-full left-0 mb-2 w-40 bg-popover border rounded-xl shadow-lg animate-in fade-in zoom-in-95 z-50 overflow-hidden"
          >
            <div className="p-1">
              {mcpOptions.map(opt => (
                <button
                  key={opt.id}
                  role="option"
                  aria-selected={selectedMcp === opt.id && searchMode === 'mcp'}
                  onClick={() => handleMcpSelect(opt.id)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2 py-2 text-xs transition-colors hover:bg-muted",
                    selectedMcp === opt.id && searchMode === 'mcp' && "bg-muted font-medium text-pink-500"
                  )}
                >
                  {opt.label}
                  {selectedMcp === opt.id && searchMode === 'mcp' && <Check className="h-3 w-3" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
