'use client'

import React, { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useI18n } from '@/lib/i18n/i18n-context'
import { Plus, Compass, LayoutGrid, FolderOpen, MessageSquare, PanelLeft, Trash2, Settings } from 'lucide-react'
import { ChatSession } from '@/types/chat'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
  onNewChat: () => void
  onSelectChat: (id: string) => void
  onDeleteChat: (id: string) => void
  onClearHistory: () => void
  onOpenSettings: () => void
  activeView: string
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
  
  // No internal state for view

  const groupedHistory = useMemo(() => {
    const groups: Record<string, typeof history> = {}
    history.forEach(item => {
        let key = item.date
        if (key === 'Just now') key = 'Today'
        if (!groups[key]) groups[key] = []
        groups[key].push(item)
    })
    return groups
  }, [history])

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
          "fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden transition-opacity duration-500",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onToggle}
      />

      {/* Sidebar Container */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col border-r bg-card/50 backdrop-blur-xl transition-all duration-300 ease-[cubic-bezier(0.2,0,0,1)] md:relative",
          isOpen ? "w-[260px] translate-x-0" : "-translate-x-full w-0 md:translate-x-0 md:w-0 md:border-r-0 overflow-hidden"
        )}
      >
        <div className="flex h-full flex-col p-3 gap-2">
          
          {/* Sidebar Header */}
          <div className="flex items-center justify-between px-2 mb-2 pt-1">
             <div className="flex items-center gap-2 select-none">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground text-xs font-bold">
                    W
                </div>
                <span className="font-bold text-base tracking-tight">{t('weaver')}</span>
             </div>
             <Button variant="ghost" size="icon" onClick={onToggle} className="h-7 w-7 text-muted-foreground">
                <PanelLeft className="h-4 w-4" />
             </Button>
          </div>

          {/* Top Actions */}
          <div className="mb-2">
             <Button 
                className={cn(
                    "w-full justify-start gap-2 h-10 shadow-sm border bg-background hover:bg-muted/50 transition-all font-medium text-sm", 
                    !isOpen && "px-2"
                )}
                variant="outline"
                onClick={onNewChat}
             >
                <Plus className="h-4 w-4" />
                <span className={cn("truncate", !isOpen && "md:hidden")}>{t('newInvestigation')}</span>
             </Button>
          </div>

          {/* Navigation Groups */}
          <div className="flex-1 overflow-y-auto space-y-6 py-2 pr-1 scrollbar-thin scrollbar-thumb-muted/50">
            
            {/* Workspace */}
            <div className="space-y-1">
               <div className="px-3 text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-1">
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
              ) : (
                  <div className="space-y-4">
                      {groupOrder.map(dateLabel => {
                          const items = groupedHistory[dateLabel]
                          if (!items || items.length === 0) return null
                          
                          return (
                              <div key={dateLabel} className="space-y-1">
                                  <div className="px-3 text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-1">
                                      {dateLabel}
                                  </div>
                                  {items.map((item) => (
                                    <div key={item.id} className="group relative">
                                        <button 
                                            onClick={() => onSelectChat(item.id)}
                                            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm transition-all duration-200 text-muted-foreground hover:bg-muted/60 hover:text-foreground text-left pr-8"
                                        >
                                            <MessageSquare className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" />
                                            <span className="truncate">{item.title}</span>
                                        </button>
                                        <button 
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                setDeleteId(item.id)
                                            }}
                                            className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-destructive transition-all"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </button>
                                    </div>
                                  ))}
                              </div>
                          )
                      })}
                      {/* Handle items that didn't fall into the main groups if any */}
                      {Object.keys(groupedHistory).filter(k => !groupOrder.includes(k)).map(dateLabel => (
                           <div key={dateLabel} className="space-y-1">
                                <div className="px-3 text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-1">
                                    {dateLabel}
                                </div>
                                {groupedHistory[dateLabel].map((item) => (
                                  <div key={item.id} className="group relative">
                                      <button 
                                          onClick={() => onSelectChat(item.id)}
                                          className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm transition-all duration-200 text-muted-foreground hover:bg-muted/60 hover:text-foreground text-left pr-8"
                                      >
                                          <MessageSquare className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" />
                                          <span className="truncate">{item.title}</span>
                                      </button>
                                      <button 
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                setDeleteId(item.id)
                                            }}
                                            className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-destructive transition-all"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </button>
                                  </div>
                                ))}
                            </div>
                      ))}
                  </div>
              )}
          </div>

          {/* Bottom Actions */}
          <div className="border-t pt-2 mt-auto">
             {history.length > 0 && (
                <button 
                    onClick={() => setShowClearConfirm(true)}
                    className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors group"
                >
                    <Trash2 className="h-4 w-4" />
                    <span>Clear History</span>
                </button>
             )}
             <button 
                onClick={onOpenSettings}
                className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-muted/60 hover:text-foreground transition-colors group"
             >
                <Settings className="h-4 w-4" />
                <span>Settings</span>
             </button>
          </div>
        </div>
      </div>
    </>
  )
}


function SidebarItem({ icon: Icon, label, active, onClick }: { icon: any, label: string, active?: boolean, onClick?: () => void }) {
    return (
        <button 
            onClick={onClick}
            className={cn(
            "flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm transition-all duration-200 group",
            active 
              ? "bg-primary/10 text-primary font-medium" 
              : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        )}>
            <Icon className={cn("h-4 w-4 transition-colors", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
            <span className="truncate">{label}</span>
        </button>
    )
}
