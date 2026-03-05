'use client'

import { useMemo, useState, useCallback, useEffect, memo } from 'react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useI18n } from '@/lib/i18n/i18n-context'
import {
  ChevronLeft,
  Compass,
  FolderOpen,
  LayoutGrid,
  Moon,
  Plus,
  Settings,
  Star,
  StarOff,
  Sun,
  Trash2,
  X,
} from '@/components/ui/icons'
import { Virtuoso } from 'react-virtuoso'
import { ChatSession } from '@/types/chat'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useTheme } from '@/components/theme-provider'
import { WORKSPACE_PANEL_W, WORKSPACE_RAIL_W } from './workspace-layout'

type HistoryGroupKey = 'today' | 'yesterday' | 'previous7' | 'older'

const GROUP_ORDER: HistoryGroupKey[] = ['today', 'yesterday', 'previous7', 'older']

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
  onNewChat: () => void
  onSelectChat: (id: string) => void
  onDeleteChat: (id: string) => void
  onTogglePin: (id: string) => void
  onRenameChat: (id: string, title: string) => void
  onClearHistory: () => void
  onOpenSettings: () => void
  activeView: string
  onViewChange: (view: string) => void
  activeChatId?: string | null
  history: ChatSession[]
  isLoading?: boolean
}

export const Sidebar = memo(function Sidebar(props: SidebarProps) {
  const {
    isOpen,
    onToggle,
    onNewChat,
    onSelectChat,
    onDeleteChat,
    onTogglePin,
    onClearHistory,
    onOpenSettings,
    activeView,
    onViewChange,
    activeChatId = null,
    history,
    isLoading = false,
  } = props
  const { t, language } = useI18n()
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [historyQuery, setHistoryQuery] = useState('')
  const [nowMs, setNowMs] = useState<number>(0)

  useEffect(() => {
    const update = () => setNowMs(Date.now())
    update()
    const id = window.setInterval(update, 60_000)
    return () => window.clearInterval(id)
  }, [])

  const effectiveNowMs = useMemo(() => {
    if (nowMs > 0) return nowMs
    const head = history[0]
    return (head?.updatedAt || head?.createdAt || 0) as number
  }, [history, nowMs])

  const toggleTheme = () => {
    const currentTheme = resolvedTheme || theme
    setTheme(currentTheme === 'dark' ? 'light' : 'dark')
  }

  const pinnedItems = useMemo(() => history.filter(s => s.isPinned), [history])
  const unpinnedItems = useMemo(() => history.filter(s => !s.isPinned), [history])

  const normalizedQuery = historyQuery.trim().toLowerCase()
  const hasQuery = normalizedQuery.length > 0

  const filteredPinnedItems = useMemo(() => {
    if (!hasQuery) return pinnedItems
    return pinnedItems.filter((s) => (s.title || '').toLowerCase().includes(normalizedQuery))
  }, [hasQuery, normalizedQuery, pinnedItems])

  const filteredUnpinnedItems = useMemo(() => {
    if (!hasQuery) return unpinnedItems
    return unpinnedItems.filter((s) => (s.title || '').toLowerCase().includes(normalizedQuery))
  }, [hasQuery, normalizedQuery, unpinnedItems])

  const groupedHistory = useMemo(() => {
    const groups: Record<HistoryGroupKey, typeof history> = {
      today: [],
      yesterday: [],
      previous7: [],
      older: [],
    }
    if (!effectiveNowMs) {
      filteredUnpinnedItems.forEach(item => groups.older.push(item))
      return groups
    }

    const now = new Date(effectiveNowMs)
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
    const yesterday = today - 86400000
    const sevenDaysAgo = today - 86400000 * 7

    filteredUnpinnedItems.forEach(item => {
      const time = item.updatedAt || item.createdAt || 0
      let key: HistoryGroupKey = 'older'
      if (time >= today) key = 'today'
      else if (time >= yesterday) key = 'yesterday'
      else if (time >= sevenDaysAgo) key = 'previous7'
      groups[key].push(item)
    })
    return groups
  }, [effectiveNowMs, filteredUnpinnedItems])

  type FlatEntry =
    | { type: 'header'; kind: 'pinned' | 'group' | 'results' | 'empty'; label: string }
    | { type: 'item'; item: ChatSession }

  const flatItems = useMemo(() => {
    const items: FlatEntry[] = []

    if (hasQuery) {
      const matches = [...filteredPinnedItems, ...filteredUnpinnedItems]
      if (matches.length === 0) {
        items.push({ type: 'header', kind: 'empty', label: '' })
        return items
      }

      items.push({ type: 'header', kind: 'results', label: '' })
      matches.forEach(item => items.push({ type: 'item', item }))
      return items
    }

    if (filteredPinnedItems.length > 0) {
      items.push({ type: 'header', kind: 'pinned', label: '' })
      filteredPinnedItems.forEach(item => items.push({ type: 'item', item }))
    }

    GROUP_ORDER.forEach(dateLabel => {
      const group = groupedHistory[dateLabel]
      if (group && group.length > 0) {
        items.push({ type: 'header', kind: 'group', label: dateLabel })
        group.forEach(item => items.push({ type: 'item', item }))
      }
    })

    return items
  }, [filteredPinnedItems, filteredUnpinnedItems, groupedHistory, hasQuery])

  const renderFlatItem = useCallback((index: number) => {
    const entry = flatItems[index]!
    if (entry.type === 'header') {
      const text =
        entry.kind === 'pinned'
          ? t('pinned')
          : entry.kind === 'results'
            ? t('results')
            : entry.kind === 'empty'
              ? t('noResults')
              : entry.label === 'today'
                ? t('groupToday')
                : entry.label === 'yesterday'
                  ? t('groupYesterday')
                  : entry.label === 'previous7'
                    ? t('groupPrevious7Days')
                    : t('groupOlder')

      return (
        <div className="px-3 pt-5 pb-1.5">
          <div className="flex items-center gap-2 text-muted-foreground">
            {entry.kind === 'pinned' ? (
              <Star className="h-3 w-3 fill-current text-primary/50" />
            ) : null}
            <span className="text-[11px] font-semibold uppercase tracking-wider">
              {text}
            </span>
          </div>
        </div>
      )
    }
    return (
      <SidebarChatItem
        item={entry.item}
        onSelect={onSelectChat}
        onDelete={setDeleteId}
        onTogglePin={onTogglePin}
        active={activeChatId === entry.item.id}
        language={language}
        nowMs={effectiveNowMs}
      />
    )
  }, [activeChatId, effectiveNowMs, flatItems, language, onSelectChat, onTogglePin, t])

  return (
    <>
      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Chat"
        description="Are you sure you want to delete this conversation? This action cannot be undone."
        onConfirm={() => deleteId && onDeleteChat(deleteId)}
        confirmText="Delete"
        variant="destructive"
      />

      <ConfirmDialog
        open={showClearConfirm}
        onOpenChange={setShowClearConfirm}
        title="Clear History"
        description="Are you sure you want to delete all chat history? This action cannot be undone."
        onConfirm={onClearHistory}
        confirmText="Clear All"
        variant="destructive"
      />

      {/* Mobile Overlay */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/25 backdrop-blur-[3px] md:hidden transition-opacity duration-300",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onToggle}
      />

      {/* Mobile Drawer */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 md:hidden",
          "w-[300px] max-w-[85vw]",
          "bg-background shadow-[0_0_60px_rgba(0,0,0,0.10)]",
          "transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
        aria-hidden={!isOpen}
      >
        <div className="flex h-full flex-col p-3 gap-3">
          <div className="flex items-center justify-between px-1 pt-1">
            <div className="flex items-center gap-2.5 select-none">
              <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-xs font-bold text-primary">
                W
              </div>
              <span className="text-sm font-semibold text-foreground">{t('weaver')}</span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggle}
              aria-label="Close sidebar"
              aria-expanded={isOpen}
              className="h-7 w-7 rounded-lg text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div>
            <Button
              className="w-full justify-start gap-2 h-9 font-medium text-sm rounded-lg"
              variant="default"
              onClick={onNewChat}
            >
              <Plus className="h-4 w-4" />
              <span className="truncate">{t('newInvestigation')}</span>
            </Button>
          </div>

          <div className="space-y-0.5" role="group" aria-label="Workspace navigation">
            <SidebarItem icon={LayoutGrid} label={t('dashboard')} active={activeView === 'dashboard'} onClick={() => onViewChange('dashboard')} iconClassName="text-sky-500 dark:text-sky-400" />
            <SidebarItem icon={Compass} label={t('discover')} active={activeView === 'discover'} onClick={() => onViewChange('discover')} iconClassName="text-amber-500 dark:text-amber-400" />
            <SidebarItem icon={FolderOpen} label={t('library')} active={activeView === 'library'} onClick={() => onViewChange('library')} iconClassName="text-violet-500 dark:text-violet-400" />
          </div>

          <div>
            <Input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              aria-label="Search chat history"
              className="h-8 text-xs font-medium rounded-lg bg-background border-transparent shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
            />
          </div>

          <div className="flex-1 min-h-0 overflow-hidden">
            {isLoading ? (
              <div className="space-y-3 px-2 py-2">
                {[1, 2, 3, 4, 5].map(i => (
                  <div key={i} className="space-y-1.5 animate-pulse">
                    <div className="h-3 w-24 bg-muted/30 rounded" />
                    <div className="h-7 w-full bg-muted/20 rounded-lg" />
                  </div>
                ))}
              </div>
            ) : history.length === 0 ? (
              <div className="px-3 text-xs font-medium text-muted-foreground italic py-4">{t('noRecentChats')}</div>
            ) : (
              <Virtuoso
                style={{ height: '100%' }}
                totalCount={flatItems.length}
                itemContent={renderFlatItem}
                className="scrollbar-thin scrollbar-thumb-muted/40"
              />
            )}
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-border/20 pt-2 px-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={toggleTheme}
              aria-label={t('toggleTheme')}
              title={t('toggleTheme')}
              className="hover:bg-accent/50 rounded-lg"
            >
              <Sun className="h-4 w-4 text-amber-500 rotate-0 scale-100 transition-transform duration-200 dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-4 w-4 text-indigo-400 rotate-90 scale-0 transition-transform duration-200 dark:rotate-0 dark:scale-100" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={onOpenSettings}
              aria-label={t('settings')}
              title={t('settings')}
              className="hover:bg-accent/50 rounded-lg"
            >
              <Settings className="h-4 w-4 text-muted-foreground" />
            </Button>
          </div>
        </div>
      </div>

      {/* Desktop Rail + Panel */}
      <aside className="hidden md:flex h-dvh shrink-0 shadow-[12px_0_44px_rgba(0,0,0,0.05)]">
        <TooltipProvider delayDuration={200}>
          <div
            className="flex h-full flex-col items-center justify-between bg-background pt-3 pb-5"
            style={{ width: WORKSPACE_RAIL_W }}
          >
            <div className="flex flex-col items-center gap-1.5">
              <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-xs font-bold text-primary select-none mb-1">
                W
              </div>

              <RailButton
                label={isOpen ? t('collapsePanel') : t('expandPanel')}
                active={false}
                onClick={onToggle}
              >
                <ChevronLeft className={cn("h-4 w-4 transition-transform duration-200", !isOpen && "rotate-180")} />
              </RailButton>

              <div className="h-px w-5 bg-border/40 my-1" />

              <RailButton
                label={t('dashboard')}
                active={activeView === 'dashboard'}
                onClick={() => onViewChange('dashboard')}
              >
                <LayoutGrid className="h-4 w-4 text-sky-500 dark:text-sky-400" />
              </RailButton>
              <RailButton
                label={t('discover')}
                active={activeView === 'discover'}
                onClick={() => onViewChange('discover')}
              >
                <Compass className="h-4 w-4 text-amber-500 dark:text-amber-400" />
              </RailButton>
              <RailButton
                label={t('library')}
                active={activeView === 'library'}
                onClick={() => onViewChange('library')}
              >
                <FolderOpen className="h-4 w-4 text-violet-500 dark:text-violet-400" />
              </RailButton>
            </div>

            <div className="flex flex-col items-center gap-1.5">
              <RailButton label={t('toggleTheme')} active={false} onClick={toggleTheme}>
                <>
                  <Sun className="h-4 w-4 text-amber-500 rotate-0 scale-100 transition-transform duration-200 dark:-rotate-90 dark:scale-0" />
                  <Moon className="absolute h-4 w-4 text-indigo-400 rotate-90 scale-0 transition-transform duration-200 dark:rotate-0 dark:scale-100" />
                </>
              </RailButton>

              <RailButton label={t('settings')} active={false} onClick={onOpenSettings}>
                <Settings className="h-4 w-4 text-muted-foreground" />
              </RailButton>
            </div>
          </div>
        </TooltipProvider>

        <div
          className={cn(
            "h-full bg-background overflow-hidden transition-[width] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          )}
          style={{ width: isOpen ? WORKSPACE_PANEL_W : 0 }}
          aria-hidden={!isOpen}
        >
          {isOpen ? (
            <div className="flex h-full flex-col p-3 gap-3">
              <div>
                <Button
                  className="w-full justify-start gap-2 h-9 shadow-none font-medium text-sm rounded-lg"
                  variant="default"
                  onClick={onNewChat}
                >
                  <Plus className="h-4 w-4" />
                  <span className="truncate">{t('newInvestigation')}</span>
                </Button>
              </div>

              <div>
                <Input
                  value={historyQuery}
                  onChange={(e) => setHistoryQuery(e.target.value)}
                  placeholder={t('searchPlaceholder')}
                  aria-label="Search chat history"
                  className="h-8 text-xs font-medium rounded-lg bg-background border-transparent shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                />
              </div>

              <div className="flex-1 min-h-0 overflow-hidden">
                {isLoading ? (
                  <div className="space-y-3 px-2 py-2">
                    {[1, 2, 3, 4, 5].map(i => (
                      <div key={i} className="space-y-1.5 animate-pulse">
                        <div className="h-3 w-24 bg-muted/30 rounded" />
                        <div className="h-7 w-full bg-muted/20 rounded-lg" />
                      </div>
                    ))}
                  </div>
                ) : history.length === 0 ? (
                  <div className="px-3 text-xs font-medium text-muted-foreground italic py-4">{t('noRecentChats')}</div>
                ) : (
                  <Virtuoso
                    style={{ height: '100%' }}
                    totalCount={flatItems.length}
                    itemContent={renderFlatItem}
                    className="scrollbar-thin scrollbar-thumb-muted/40"
                  />
                )}
              </div>

              <div className="border-t border-border/20 pt-2 px-1 flex items-center justify-between">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowClearConfirm(true)}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  {t('clearHistory')}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </>
  )
})

function RailButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          aria-label={label}
          aria-current={active ? 'page' : undefined}
          className={cn(
            "relative flex size-9 items-center justify-center rounded-lg transition-all duration-150",
            active
              ? "bg-primary/10 text-primary shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          )}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  )
}

function formatRelativeTime(timestampMs: number, language: string, nowMs: number): string {
  const ts = Number(timestampMs)
  if (!Number.isFinite(ts) || ts <= 0) return ''

  const baseNow = Number(nowMs)
  if (!Number.isFinite(baseNow) || baseNow <= 0) return ''

  const deltaMs = Math.max(0, baseNow - ts)

  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  const week = 7 * day

  const locale =
    language === 'zh'
      ? 'zh-CN'
      : language === 'ja'
        ? 'ja-JP'
        : language === 'ko'
          ? 'ko-KR'
          : 'en'

  const formatWithRtf = (value: number, unit: Intl.RelativeTimeFormatUnit): string => {
    try {
      const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'narrow' })
      return rtf.format(-value, unit)
    } catch {
      const suffix = unit === 'minute'
        ? 'm'
        : unit === 'hour'
          ? 'h'
          : unit === 'day'
            ? 'd'
            : unit === 'week'
              ? 'w'
              : ''
      return suffix ? `${value}${suffix}` : `${value}`
    }
  }

  if (deltaMs < minute) {
    return language === 'zh' ? '刚刚' : 'now'
  }
  if (deltaMs < hour) {
    return formatWithRtf(Math.round(deltaMs / minute), 'minute')
  }
  if (deltaMs < day) {
    return formatWithRtf(Math.round(deltaMs / hour), 'hour')
  }
  if (deltaMs < week) {
    return formatWithRtf(Math.round(deltaMs / day), 'day')
  }
  return formatWithRtf(Math.round(deltaMs / week), 'week')
}

function SidebarChatItem({
  item,
  onSelect,
  onDelete,
  onTogglePin,
  active,
  language,
  nowMs,
}: {
  item: ChatSession
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onTogglePin: (id: string) => void
  active: boolean
  language: string
  nowMs: number
}) {
  const time = item.updatedAt || item.createdAt || 0
  const timeLabel = time ? formatRelativeTime(time, language, nowMs) : ''
  const summary = (item.summary || '').trim()

  return (
    <div className="group relative px-1.5 py-0.5" role="listitem">
      <button
        onClick={() => onSelect(item.id)}
        aria-label={`Open chat: ${item.title}`}
        aria-current={active ? 'page' : undefined}
        className={cn(
          "flex w-full gap-3 px-2.5 py-2 rounded-lg text-left transition-all duration-150 pr-10",
          active
            ? "bg-primary/[0.05] text-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-accent/30"
        )}
      >
        {active && (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-primary" />
        )}

        <span className="min-w-0 flex-1">
          <span className="flex items-center justify-between gap-2">
            <span className={cn(
              "truncate text-[13px] font-medium",
              active ? "text-foreground" : "text-foreground"
            )}>
              {item.title}
            </span>
            <span className="shrink-0 text-[11px] font-medium tabular-nums text-muted-foreground">
              {timeLabel}
            </span>
          </span>
          {summary ? (
            <span className="mt-0.5 block text-xs font-medium leading-4 text-muted-foreground line-clamp-1">
              {summary}
            </span>
          ) : null}
        </span>
      </button>

      <div
        className={cn(
          "absolute right-3 top-1/2 -translate-y-1/2",
          "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity duration-150",
        )}
      >
        <div className="flex items-center gap-0.5 rounded-md p-0.5">
          <button
            onClick={(e) => {
              e.stopPropagation()
              onTogglePin(item.id)
            }}
            aria-label={item.isPinned ? `Unpin ${item.title}` : `Pin ${item.title}`}
            aria-pressed={item.isPinned}
            className={cn(
              "p-1 rounded text-muted-foreground transition-colors",
              "hover:bg-accent hover:text-foreground",
              item.isPinned && "text-primary"
            )}
          >
            {item.isPinned ? (
              <StarOff className="h-3 w-3" />
            ) : (
              <Star className="h-3 w-3" />
            )}
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete(item.id)
            }}
            aria-label={`Delete ${item.title}`}
            className="p-1 rounded text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  )
}


function SidebarItem({ icon: Icon, label, active, onClick, iconClassName }: { icon: any, label: string, active?: boolean, onClick?: () => void, iconClassName?: string }) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn(
        "sidebar-item group",
        active && "active"
      )}>
      <Icon className={cn("h-4 w-4 transition-colors", iconClassName || (active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"))} />
      <span className="truncate text-sm">{label}</span>
    </button>
  )
}
