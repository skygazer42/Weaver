'use client'

import React, { useMemo, useState } from 'react'
import Image from 'next/image'
import logo from '@/public/logo.png'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useI18n } from '@/lib/i18n/i18n-context'
import { Plus, Compass, LayoutGrid, FolderOpen, MessageSquare, PanelLeft, Trash2, Pin, PinOff, type LucideIcon } from 'lucide-react'
import { ChatSession } from '@/types/chat'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

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
  activeSessionId?: string | null
  onViewChange: (view: string) => void
  history: ChatSession[]
  isLoading?: boolean
}

export function Sidebar({ 
    isOpen, 
    onToggle, 
    onNewChat, 
    onSelectChat, 
    onDeleteChat,
    onTogglePin,
    onClearHistory,
    activeView, 
    activeSessionId,
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
        const time = item.updatedAt || item.createdAt || today
        let key = 'Older'
        if (time >= today) key = 'Today'
        else if (time >= yesterday) key = 'Yesterday'
        else if (time >= sevenDaysAgo) key = 'Previous 7 Days'
        
        if (!groups[key]) groups[key] = []
        groups[key].push(item)
    })
    return groups
  }, [unpinnedItems])

  const groupOrder = ['Today', 'Yesterday', 'Previous 7 Days', 'Older']

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
          "fixed inset-0 z-40 bg-foreground/20 backdrop-blur-[2px] transition-opacity duration-200 dark:bg-black/60 md:hidden",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onToggle}
      />

      {/* Sidebar Container */}
      <div
        inert={!isOpen}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex shrink-0 flex-col border-r border-border/80 bg-surface-subtle transition-[width,transform] duration-200 ease-out md:relative",
          isOpen ? "w-[260px] translate-x-0" : "-translate-x-full w-0 md:translate-x-0 md:w-0 md:border-r-0 overflow-hidden"
        )}
      >
        <div className="flex h-full w-[260px] flex-col gap-3 p-3 pt-0">
          
          {/* Sidebar Header */}
          <div className="-mx-3 flex h-14 shrink-0 items-center justify-between border-b border-border/80 px-4">
             <div className="flex items-center gap-2 select-none">
                <Image src={logo} alt="" width={28} height={28} className="shrink-0 object-contain" />
                <span className="text-base font-semibold tracking-tight">{t('weaver')}</span>
             </div>
             <Button type="button" variant="ghost" size="icon" onClick={onToggle} aria-label="Collapse sidebar" className="text-muted-foreground">
                <PanelLeft className="h-4 w-4" />
             </Button>
          </div>

          {/* Top Actions */}
          <div className="mb-2">
             <Button 
                className={cn(
                    "h-9 w-full justify-start gap-2 border-border bg-card text-sm font-medium shadow-xs hover:bg-accent/60",
                    !isOpen && "px-2"
                )}
                variant="outline"
                type="button"
                onClick={onNewChat}
             >
                <Plus className="h-4 w-4" />
                <span className={cn("truncate", !isOpen && "md:hidden")}>{t('newInvestigation')}</span>
             </Button>
          </div>

          {/* Navigation Groups */}
          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto py-1">
            
            {/* Workspace */}
            <div className="space-y-1">
               <div className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
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
                  <div className="px-3 py-2 text-xs text-muted-foreground">{t('noRecentChats')}</div>
              ) : (
                  <div className="space-y-4">
                      {/* Pinned Section */}
                      {pinnedItems.length > 0 && (
                          <div className="space-y-1">
                              <div className="mb-2 flex items-center gap-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                  <Pin className="h-3 w-3 fill-primary" /> Pinned
                              </div>
                              {pinnedItems.map(item => (
                                  <SidebarChatItem 
                                    key={item.id} 
                                    item={item} 
                                    active={activeView === 'dashboard' && activeSessionId === item.id}
                                    onSelect={onSelectChat} 
                                    onDelete={setDeleteId} 
                                    onTogglePin={onTogglePin}
                                  />
                              ))}
                          </div>
                      )}

                      {/* Grouped Recent Section */}
                      {groupOrder.map(dateLabel => {
                          const items = groupedHistory[dateLabel]
                          if (!items || items.length === 0) return null
                          
                          return (
                              <div key={dateLabel} className="space-y-1">
                                  <div className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                      {dateLabel}
                                  </div>
                                  {items.map((item) => (
                                      <SidebarChatItem 
                                        key={item.id} 
                                        item={item} 
                                        active={activeView === 'dashboard' && activeSessionId === item.id}
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
          </div>

          {/* Bottom Actions - Removed Settings and Clear History as requested */}
        </div>
      </div>
    </>
  )
}

function SidebarChatItem({ 
    item, 
    active,
    onSelect, 
    onDelete, 
    onTogglePin 
}: { 
    item: ChatSession, 
    active: boolean,
    onSelect: (id: string) => void, 
    onDelete: (id: string) => void,
    onTogglePin: (id: string) => void
}) {
    return (
        <div className={cn("group relative rounded-md", active && "bg-card shadow-xs")}>
            {active && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" />}
            <button 
                type="button"
                aria-label={item.title}
                aria-current={active ? 'page' : undefined}
                title={item.title}
                onClick={() => onSelect(item.id)}
                className={cn(
                    "flex w-full items-center gap-2.5 rounded-md px-3 py-2 pr-16 text-left text-sm transition-colors hover:bg-accent/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
                    active ? "font-medium text-foreground" : "text-muted-foreground"
                )}
            >
                <MessageSquare className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" />
                <span className="truncate">{item.title}</span>
            </button>
            <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center rounded-md bg-surface-subtle opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
                <button 
                    type="button"
                    aria-label={`${item.isPinned ? 'Unpin' : 'Pin'} ${item.title}`}
                    onClick={(e) => {
                        e.stopPropagation()
                        onTogglePin(item.id)
                    }}
                    className={cn(
                        "flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                        item.isPinned && "text-primary"
                    )}
                >
                    {item.isPinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
                </button>
                <button 
                    type="button"
                    aria-label={`Delete ${item.title}`}
                    onClick={(e) => {
                        e.stopPropagation()
                        onDelete(item.id)
                    }}
                    className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-destructive-surface hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                >
                    <Trash2 className="h-3.5 w-3.5" />
                </button>
            </div>
        </div>
    )
}


function SidebarItem({ icon: Icon, label, active, onClick }: { icon: LucideIcon, label: string, active?: boolean, onClick?: () => void }) {
    return (
        <button 
            type="button"
            aria-current={active ? 'page' : undefined}
            onClick={onClick}
            className={cn(
            "group flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
            active 
              ? "bg-accent/70 font-medium text-foreground"
              : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
        )}>
            <Icon className={cn("h-4 w-4 transition-colors", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
            <span className="truncate">{label}</span>
        </button>
    )
}
