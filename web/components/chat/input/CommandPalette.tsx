'use client'

import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { Bot, Globe, Bug, BookOpen, PenTool, TestTube, Trash2, Rocket, Search } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'

interface Command {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  desc: string
}

interface CommandPaletteProps {
  show: boolean
  onSelect: (commandId: string) => void
  onClose: () => void
}

// All available commands
const ALL_COMMANDS: Command[] = [
  { id: 'agent', label: 'Agent Mode', icon: Bot, desc: 'Plan & web search' },
  { id: 'ultra', label: 'Deep Research', icon: Rocket, desc: 'Deep research (agent + deep search)' },
  { id: 'web', label: 'Web Mode', icon: Globe, desc: 'Web search only' },
  { id: 'fix', label: 'Fix Code', icon: Bug, desc: 'Debug & Fix' },
  { id: 'explain', label: 'Explain', icon: BookOpen, desc: 'Explain concept' },
  { id: 'refactor', label: 'Refactor', icon: PenTool, desc: 'Optimize code' },
  { id: 'test', label: 'Write Tests', icon: TestTube, desc: 'Generate tests' },
  { id: 'clear', label: 'Clear Chat', icon: Trash2, desc: 'Reset conversation' },
]

export function CommandPalette({ show, onSelect, onClose }: CommandPaletteProps) {
  const { t } = useI18n()
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Filter commands based on search query
  const filteredCommands = useMemo(() => {
    if (!searchQuery.trim()) return ALL_COMMANDS

    const query = searchQuery.toLowerCase()
    return ALL_COMMANDS.filter(cmd =>
      cmd.label.toLowerCase().includes(query) ||
      cmd.desc.toLowerCase().includes(query) ||
      cmd.id.toLowerCase().includes(query)
    )
  }, [searchQuery])

  // Reset selection when menu opens or filter changes
  useEffect(() => {
    if (show) {
      setSelectedIndex(0)
      setSearchQuery('')
    }
  }, [show])

  useEffect(() => {
    setSelectedIndex(0)
  }, [filteredCommands.length])

  // Keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(i => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (filteredCommands[selectedIndex]) {
          onSelect(filteredCommands[selectedIndex].id)
        }
        break
      case 'Escape':
        e.preventDefault()
        onClose()
        break
    }
  }, [filteredCommands, selectedIndex, onSelect, onClose])

  // Focus input for search
  useEffect(() => {
    if (show && inputRef.current) {
      inputRef.current.focus()
    }
  }, [show])

  if (!show) return null

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      role="listbox"
      aria-label="Commands"
      className="absolute bottom-full left-4 mb-2 w-72 bg-popover border rounded-xl shadow-xl overflow-hidden animate-in slide-in-from-bottom-2 fade-in z-50 focus:outline-none"
    >
      {/* Search Input */}
      <div className="px-3 py-2 border-b bg-muted/30">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search commands..."
            className="w-full pl-7 pr-2 py-1.5 text-sm bg-transparent border-none focus:outline-none placeholder:text-muted-foreground/60"
          />
        </div>
      </div>

      {/* Header */}
      <div className="px-3 py-1.5 text-xs font-semibold text-muted-foreground bg-muted/50 border-b">
        {t('commands')} {filteredCommands.length !== ALL_COMMANDS.length && `(${filteredCommands.length})`}
      </div>

      {/* Commands List */}
      <div className="p-1 max-h-64 overflow-y-auto scrollbar-thin">
        {filteredCommands.length === 0 ? (
          <div className="px-3 py-4 text-center text-sm text-muted-foreground">
            No commands found
          </div>
        ) : (
          filteredCommands.map((cmd, index) => {
            const Icon = cmd.icon
            const isSelected = index === selectedIndex
            return (
              <button
                key={cmd.id}
                role="option"
                aria-selected={isSelected}
                onClick={() => onSelect(cmd.id)}
                onMouseEnter={() => setSelectedIndex(index)}
                className={cn(
                  "flex items-center gap-3 w-full px-2 py-2 text-sm rounded-lg text-left transition-colors",
                  isSelected
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <div className="flex items-center justify-center h-6 w-6 rounded bg-background border shadow-sm">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="font-medium">{cmd.label}</div>
                  <div className="text-[10px] text-muted-foreground">{cmd.desc}</div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
