'use client'

import { useMemo, memo } from 'react'
import { Button } from '@/components/ui/button'
import { Menu, Settings, Sun, Moon, PanelRight, Share, MessageSquare, Download } from '@/components/ui/icons'
import { useTheme } from '@/components/theme-provider'
import { useI18n } from '@/lib/i18n/i18n-context'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface HeaderProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  selectedModel: string
  onModelChange: (model: string) => void
  onOpenSettings: () => void
  onToggleInspector?: () => void
  hasInspector?: boolean
  currentView: 'dashboard' | 'discover' | 'library'
  sessionTitle?: string | null
  threadId?: string | null
  onOpenShare?: () => void
  onOpenComments?: () => void
  onOpenExport?: () => void
}

export const Header = memo(function Header({
  sidebarOpen,
  onToggleSidebar,
  selectedModel,
  onModelChange,
  onOpenSettings,
  onToggleInspector,
  hasInspector,
  currentView,
  sessionTitle,
  threadId,
  onOpenShare,
  onOpenComments,
  onOpenExport,
}: HeaderProps) {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const { t } = useI18n()

  const toggleTheme = () => {
    const currentTheme = resolvedTheme || theme
    setTheme(currentTheme === 'dark' ? 'light' : 'dark')
  }

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
      { id: 'qwen3-vl-flash', name: 'qwen3-vl-flash', provider: t('qwen') },
      { id: 'glm-4.6', name: 'GLM-4.6', provider: t('zhipu') },
      { id: 'glm-4.6v', name: 'glm-4.6v', provider: t('zhipu') },
    ],
    [t],
  )

  const currentModelName = useMemo(
    () => models.find((m) => m.id === selectedModel)?.name || selectedModel,
    [models, selectedModel],
  )

  const viewLabel = useMemo(() => {
    return t(currentView)
  }, [currentView, t])

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border/10 bg-background px-5 transition-colors duration-200">
      <div className="flex items-center gap-4 min-w-0">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleSidebar}
          className="rounded-lg hover:bg-accent md:hidden"
          aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          aria-expanded={sidebarOpen}
        >
          <Menu className="h-[18px] w-[18px] text-slate-500 dark:text-slate-400" />
        </Button>

        <div className="min-w-0">
          <div className="text-sm font-semibold text-foreground truncate text-balance">
            {viewLabel}
          </div>
          {currentView === 'dashboard' ? (
            <div className="text-xs font-medium text-muted-foreground truncate text-pretty">
              {sessionTitle || t('newInvestigation')}
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        {currentView === 'dashboard' && threadId ? (
          <>
            <Button
              variant="ghost"
              size="icon"
              onClick={onOpenShare}
              className="rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent"
              aria-label="Share session"
              title="Share"
            >
              <Share className="h-[18px] w-[18px] text-sky-500 dark:text-sky-400" />
            </Button>

            <Button
              variant="ghost"
              size="icon"
              onClick={onOpenComments}
              className="rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent"
              aria-label="Open comments"
              title="Comments"
            >
              <MessageSquare className="h-[18px] w-[18px] text-violet-500 dark:text-violet-400" />
            </Button>

            <Button
              variant="ghost"
              size="icon"
              onClick={onOpenExport}
              className="rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent"
              aria-label="Export report"
              title="Export"
            >
              <Download className="h-[18px] w-[18px] text-emerald-500 dark:text-emerald-400" />
            </Button>
          </>
        ) : null}

        {hasInspector && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleInspector}
            className="rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent xl:hidden"
            aria-label="Toggle inspector"
          >
            <PanelRight className="h-[18px] w-[18px] text-slate-500 dark:text-slate-400" />
          </Button>
        )}

        <Select value={selectedModel} onValueChange={onModelChange}>
          <SelectTrigger
            aria-label="Select model"
            className="h-8 w-auto min-w-[120px] rounded-lg border-border/30 bg-muted/20 px-3 py-1.5 text-xs font-medium shadow-none transition-colors duration-200 hover:bg-accent focus:ring-offset-0"
          >
            <SelectValue placeholder={currentModelName} />
          </SelectTrigger>
          <SelectContent className="w-64 max-h-80 rounded-xl border-border/30 bg-popover/90 backdrop-blur-xl">
            {models.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                <span className="font-medium">{model.name}</span>
                <span className="ml-1.5 text-muted-foreground">({model.provider})</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            className="rounded-lg hover:bg-accent"
            aria-label={t('toggleTheme')}
          >
            <Sun className="h-[18px] w-[18px] text-amber-500 rotate-0 scale-100 transition-transform duration-200 dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-[18px] w-[18px] text-indigo-400 rotate-90 scale-0 transition-transform duration-200 dark:rotate-0 dark:scale-100" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={onOpenSettings}
            className="rounded-lg hover:bg-accent"
            aria-label={t('settings')}
          >
            <Settings className="h-[18px] w-[18px] text-slate-500 dark:text-slate-400" />
          </Button>
        </div>
      </div>
    </header>
  )
})
