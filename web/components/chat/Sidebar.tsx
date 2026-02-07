'use client'

import React, { useMemo, useState, useCallback, memo } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useI18n } from '@/lib/i18n/i18n-context'
import { Plus, Compass, LayoutGrid, FolderOpen, MessageSquare, PanelLeft, Trash2, Settings, Pin, PinOff } from 'lucide-react'
import { Virtuoso } from 'react-virtuoso'
import { ChatSession } from '@/types/chat'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

// Constant group order - defined outside component to avoid recreating on each render
const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 Days', 'Older'] as const

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
  history: ChatSession[]
  isLoading?: boolean
}

export const Sidebar = memo(function Sidebar({
    isOpen,
    onToggle,
    onNewChat,
    onSelectChat,
    onDeleteChat,
    onTogglePin,
    onRenameChat,
    onClearHistory,
    onOpenSettings,
    activeView,
    onViewChange,
    history,
    isLoading = false
}: SidebarProps) {
  const { t } = useI18n()
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)

  const pinnedItems = useMemo(() => history.filter(s => s.isPinned), [history])
  const unpinnedItems = useMemo(() => history.filter(s => !s.isPinned), [history])

  const groupedHistory = useMemo(() => {
    const groups: Record<string, typeof history> = {}
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
    const yesterday = today - 86400000
    const sevenDaysAgo = today - 86400000 * 7

    unpinnedItems.forEach(item => {
        const time = item.updatedAt || item.createdAt || Date.now()
        let key = 'Older'
        if (time >= today) key = 'Today'
        else if (time >= yesterday) key = 'Yesterday'
        else if (time >= sevenDaysAgo) key = 'Previous 7 Days'

        if (!groups[key]) groups[key] = []
        groups[key].push(item)
    })
    return groups
  }, [unpinnedItems])

  // Build a flat list of items with group headers for virtual scrolling
  const flatItems = useMemo(() => {
    const items: Array<{ type: 'header'; label: string } | { type: 'item'; item: ChatSession }> = []

    if (pinnedItems.length > 0) {
      items.push({ type: 'header', label: 'Pinned' })
      pinnedItems.forEach(item => items.push({ type: 'item', item }))
    }

    GROUP_ORDER.forEach(dateLabel => {
      const group = groupedHistory[dateLabel]
      if (group && group.length > 0) {
        items.push({ type: 'header', label: dateLabel })
        group.forEach(item => items.push({ type: 'item', item }))
      }
    })

    return items
  }, [pinnedItems, groupedHistory])

  // Virtuoso item renderer
  const renderFlatItem = useCallback((index: number) => {
    const entry = flatItems[index]
    if (entry.type === 'header') {
      return (
        <div className={cn(
          "px-3 text-[10px] font-semibold uppercase tracking-widest mb-1 pt-3",
          entry.label === 'Pinned' ? "text-primary flex items-center gap-1" : "text-muted-foreground/70"
        )}>
          {entry.label === 'Pinned' && <Pin className="h-3 w-3 fill-primary" />}
          {entry.label}
        </div>
      )
    }
    return (
      <SidebarChatItem
        item={entry.item}
        onSelect={onSelectChat}
        onDelete={setDeleteId}
        onTogglePin={onTogglePin}
      />
    )
  }, [flatItems, onSelectChat, onTogglePin])

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
          "fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden transition-opacity duration-500",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onToggle}
      />

      {/* Sidebar Container */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col sidebar transition-all duration-300 ease-out md:relative",
          isOpen ? "w-[260px] translate-x-0" : "-translate-x-full w-0 md:translate-x-0 md:w-0 md:border-r-0 overflow-hidden"
        )}
      >
        <div className="flex h-full flex-col p-3 gap-2">

          {/* Sidebar Header */}
          <div className="flex items-center justify-between px-2 mb-2 pt-1">
             <div className="flex items-center gap-2 select-none">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg gradient-accent text-white text-xs font-bold shadow-glow-sm">
                    W
                </div>
                <span className="font-bold text-base tracking-tight gradient-text">{t('weaver')}</span>
             </div>
             <Button
               variant="ghost"
               size="icon"
               onClick={onToggle}
               aria-label={isOpen ? "Close sidebar" : "Open sidebar"}
               aria-expanded={isOpen}
               className="h-7 w-7 text-muted-foreground hover:text-foreground"
             >
                <PanelLeft className="h-4 w-4" />
             </Button>
          </div>

          {/* Top Actions */}
          <div className="mb-2">
             <Button
                className={cn(
                    "w-full justify-start gap-2 h-10 shadow-sm transition-all font-medium text-sm",
                    !isOpen && "px-2"
                )}
                variant="gradient"
                onClick={onNewChat}
             >
                <Plus className="h-4 w-4" />
                <span className={cn("truncate", !isOpen && "md:hidden")}>{t('newInvestigation')}</span>
             </Button>
          </div>

          {/* Navigation Groups */}
          <nav aria-label="Workspace navigation" className="flex-1 overflow-y-auto space-y-6 py-2 pr-1 scrollbar-thin scrollbar-thumb-muted/50">

            {/* Workspace */}
            <div className="space-y-1" role="group" aria-labelledby="workspace-heading">
               <div id="workspace-heading" className="px-3 text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-1">
                 {t('workspace')}
               </div>
               <SidebarItem icon={LayoutGrid} label={t('dashboard')} active={activeView === 'dashboard'} onClick={() => onViewChange('dashboard')} />
               <SidebarItem icon={Compass} label={t('discover')} active={activeView === 'discover'} onClick={() => onViewChange('discover')} />
               <SidebarItem icon={FolderOpen} label={t('library')} active={activeView === 'library'} onClick={() => onViewChange('library')} />
            </div>

            {/* History Section */}
            {isLoading ? (
                  <div className="space-y-2 px-1">
                      {[1,2,3].map(i => (
                          <div key={i} className="h-8 w-full rounded-md bg-muted/40 animate-pulse" />
                      ))}
                  </div>
              ) : history.length === 0 ? (
                  <div className="px-3 text-xs text-muted-foreground italic py-2">{t('noRecentChats')}</div>
              ) : flatItems.length > 20 ? (
                  // Virtual scrolling for large history lists
                  <Virtuoso
                    style={{ height: 'calc(100vh - 280px)' }}
                    totalCount={flatItems.length}
                    itemContent={renderFlatItem}
                    className="scrollbar-thin scrollbar-thumb-muted/50"
                  />
              ) : (
                  <div className="space-y-4">
                      {/* Pinned Section */}
                      {pinnedItems.length > 0 && (
                          <div className="space-y-1">
                              <div className="px-3 text-[10px] font-semibold text-primary uppercase tracking-widest mb-1 flex items-center gap-1">
                                  <Pin className="h-3 w-3 fill-primary" /> Pinned
                              </div>
                              {pinnedItems.map(item => (
                                  <SidebarChatItem
                                    key={item.id}
                                    item={item}
                                    onSelect={onSelectChat}
                                    onDelete={setDeleteId}
                                    onTogglePin={onTogglePin}
                                  />
                              ))}
                          </div>
                      )}

                      {/* Grouped Recent Section */}
                      {GROUP_ORDER.map(dateLabel => {
                          const items = groupedHistory[dateLabel]
                          if (!items || items.length === 0) return null

                          return (
                              <div key={dateLabel} className="space-y-1">
                                  <div className="px-3 text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-1">
                                      {dateLabel}
                                  </div>
                                  {items.map((item) => (
                                      <SidebarChatItem
                                        key={item.id}
                                        item={item}
                                        onSelect={onSelectChat}
                                        onDelete={setDeleteId}
                                        onTogglePin={onTogglePin}
                                      />
                                  ))}
                              </div>
                          )
                      })}
                  </div>
              )}
          </nav>

          {/* Bottom Actions - Removed Settings and Clear History as requested */}
        </div>
      </div>
    </>
  )
})

function SidebarChatItem({
    item,
    onSelect,
    onDelete,
    onTogglePin
}: {
    item: ChatSession,
    onSelect: (id: string) => void,
    onDelete: (id: string) => void,
    onTogglePin: (id: string) => void
}) {
    return (
        <div className="group relative" role="listitem">
            <button
                onClick={() => onSelect(item.id)}
                aria-label={`Open chat: ${item.title}`}
                className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm transition-all duration-200 text-muted-foreground hover:bg-muted/60 hover:text-foreground text-left pr-12"
            >
                <MessageSquare className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" aria-hidden="true" />
                <span className="truncate">{item.title}</span>
            </button>
            <div className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 flex items-center transition-all bg-gradient-to-l from-muted/60 pl-2">
                <button
                    onClick={(e) => {
                        e.stopPropagation()
                        onTogglePin(item.id)
                    }}
                    aria-label={item.isPinned ? `Unpin ${item.title}` : `Pin ${item.title}`}
                    aria-pressed={item.isPinned}
                    className={cn(
                        "p-1 text-muted-foreground hover:text-primary transition-all",
                        item.isPinned && "text-primary"
                    )}
                >
                    {item.isPinned ? <PinOff className="h-3.5 w-3.5" aria-hidden="true" /> : <Pin className="h-3.5 w-3.5" aria-hidden="true" />}
                </button>
                <button
                    onClick={(e) => {
                        e.stopPropagation()
                        onDelete(item.id)
                    }}
                    aria-label={`Delete ${item.title}`}
                    className="p-1 text-muted-foreground hover:text-destructive transition-all"
                >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
            </div>
        </div>
    )
}


function SidebarItem({ icon: Icon, label, active, onClick }: { icon: any, label: string, active?: boolean, onClick?: () => void }) {
    return (
        <button
            onClick={onClick}
            aria-current={active ? 'page' : undefined}
            className={cn(
            "sidebar-item",
            active && "active"
        )}>
            <Icon className={cn("h-4 w-4 transition-colors", active ? "text-blue-500" : "text-muted-foreground group-hover:text-foreground")} aria-hidden="true" />
            <span className="truncate">{label}</span>
        </button>
    )
}
