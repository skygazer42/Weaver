'use client'

import React, { useState, useRef, useEffect, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { PanelLeft, Sun, Moon, ChevronDown, Check, LayoutPanelLeft, Settings } from 'lucide-react'
import { useTheme } from '@/components/theme-provider'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'

interface HeaderProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  selectedModel: string
  onModelChange: (model: string) => void
  onOpenSettings: () => void
  onToggleArtifacts?: () => void
  hasArtifacts?: boolean
}

export function Header({
  sidebarOpen,
  onToggleSidebar,
  selectedModel,
  onModelChange,
  onOpenSettings,
  onToggleArtifacts,
  hasArtifacts
}: HeaderProps) {
  const { theme, setTheme } = useTheme()
  const { t } = useI18n()
  const [isModelOpen, setIsModelOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const toggleTheme = () => {
    if (theme === 'dark') setTheme('light')
    else setTheme('dark')
  }

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!isModelOpen) return

    function handleClickOutside(event: PointerEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsModelOpen(false)
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsModelOpen(false)
      }
    }
    document.addEventListener('pointerdown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('pointerdown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [isModelOpen])

  const models = useMemo(
    () => [
      { id: 'gpt-5', name: 'GPT-5', provider: 'OpenAI' },
      { id: 'gpt-4.1', name: 'GPT-4.1', provider: 'OpenAI' },
      { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' },
      { id: 'claude-sonnet-4-5-20250514', name: 'Claude Sonnet 4.5', provider: 'Anthropic' },
      { id: 'claude-opus-4-20250514', name: 'Claude Opus 4', provider: 'Anthropic' },
      { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4', provider: 'Anthropic' },
      { id: 'deepseek-chat', name: 'deepseek-chat', provider: t('deepseek') },
      { id: 'deepseek-reasoner', name: 'deepseek-reasoner', provider: t('deepseek') },
      { id: 'qwen-plus', name: 'qwen-plus', provider: t('qwen') },
      { id: 'qwen3-vl-flash', name: 'qwen3-vl-flash 🖼️', provider: t('qwen') },
      { id: 'glm-4.6', name: 'GLM-4.6', provider: t('zhipu') },
      { id: 'glm-4.6v', name: 'glm-4.6v 🖼️', provider: t('zhipu') },
    ],
    [t],
  )

  const currentModelName = useMemo(
    () => models.find((m) => m.id === selectedModel)?.name || selectedModel,
    [models, selectedModel],
  )

  return (
    <header className="flex h-16 items-center justify-between border-b px-4 bg-background/80 backdrop-blur-md sticky top-0 z-30 transition-all">
      <div className="flex items-center gap-3">
        {!sidebarOpen && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleSidebar}
              className="hidden md:flex hover:bg-muted/50 rounded-full"
            >
              <PanelLeft className="h-5 w-5 text-muted-foreground" />
            </Button>
        )}
      </div>

      <div className="flex items-center gap-2">
         {/* Artifacts Toggle (Mobile/Tablet) */}
         {hasArtifacts && (
             <Button
                variant="ghost"
                size="icon"
                onClick={onToggleArtifacts}
                className="xl:hidden hover:bg-muted/50 rounded-full text-orange-500"
             >
                <LayoutPanelLeft className="h-5 w-5" />
             </Button>
         )}

                  {/* Custom Model Dropdown - Refreshed */}
                  <div className="relative" ref={dropdownRef}>
                     <button
                       onClick={() => setIsModelOpen(!isModelOpen)}
                       className="flex items-center gap-2 px-3 py-1.5 rounded-full border bg-muted/20 hover:bg-muted/50 text-sm font-medium transition-colors"
                     >
                       <span>{currentModelName}</span>
                       <ChevronDown className={cn("h-3.5 w-3.5 opacity-50 transition-transform", isModelOpen && "rotate-180")} />
                     </button>

                     {isModelOpen && (
                       <div className="absolute right-0 top-full mt-2 w-56 max-h-80 overflow-y-auto rounded-xl border bg-popover p-1 shadow-lg animate-in fade-in zoom-in-95 z-50">
                         {models.map((model) => (
                           <button
                             key={model.id}
                             onClick={() => {
                               onModelChange(model.id)
                               setIsModelOpen(false)
                             }}
                             className={cn(
                               "flex w-full items-center justify-between rounded-lg px-2 py-2 text-sm transition-colors hover:bg-muted",
                               selectedModel === model.id && "bg-muted font-medium text-primary"
                             )}
                           >
                             {model.name}
                             {selectedModel === model.id && <Check className="h-3.5 w-3.5" />}
                           </button>
                         ))}
                       </div>
                     )}
                  </div>

                  <Button
                    variant="ghost"           size="icon"
           onClick={toggleTheme}
           className="rounded-full hover:bg-muted/50"
         >
            <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
            <span className="sr-only">Toggle theme</span>
         </Button>

         <Button
           variant="ghost"
           size="icon"
           onClick={onOpenSettings}
           className="rounded-full hover:bg-muted/50"
         >
            <Settings className="h-5 w-5" />
            <span className="sr-only">Settings</span>
         </Button>
      </div>
    </header>
  )
}
