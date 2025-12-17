'use client'

import React, { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Plus, Compass, LayoutGrid, FolderOpen, MessageSquare, PanelLeft } from 'lucide-react'

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
  onNewChat: () => void
  history: Array<{ id: string, title: string, date: string }>
  isLoading?: boolean
}

export function Sidebar({ isOpen, onToggle, onNewChat, history, isLoading = false }: SidebarProps) {
  
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
                <span className="font-bold text-base tracking-tight">Weaver</span>
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
                <span className={cn("truncate", !isOpen && "md:hidden")}>New Investigation</span>
             </Button>
          </div>

          {/* Navigation Groups */}
          <div className="flex-1 overflow-y-auto space-y-6 py-2 pr-1 scrollbar-thin scrollbar-thumb-muted/50">
            
            {/* Workspace */}
            <div className="space-y-1">
               <div className="px-3 text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-1">
                 Workspace
               </div>
               <SidebarItem icon={LayoutGrid} label="Dashboard" active />
               <SidebarItem icon={Compass} label="Discover" />
               <SidebarItem icon={FolderOpen} label="Library" />
            </div>

            {/* History Section */}
            {isLoading ? (
                  <div className="space-y-2 px-1">
                      {[1,2,3].map(i => (
                          <div key={i} className="h-8 w-full rounded-md bg-muted/40 animate-pulse" />
                      ))}
                  </div>
              ) : history.length === 0 ? (
                  <div className="px-3 text-xs text-muted-foreground italic py-2">No recent chats</div>
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
                                    <button 
                                        key={item.id}
                                        className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm transition-all duration-200 text-muted-foreground hover:bg-muted/60 hover:text-foreground group text-left"
                                    >
                                        <MessageSquare className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" />
                                        <span className="truncate">{item.title}</span>
                                    </button>
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
                                  <button 
                                      key={item.id}
                                      className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm transition-all duration-200 text-muted-foreground hover:bg-muted/60 hover:text-foreground group text-left"
                                  >
                                      <MessageSquare className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" />
                                      <span className="truncate">{item.title}</span>
                                  </button>
                                ))}
                            </div>
                      ))}
                  </div>
              )}
          </div>
        </div>
      </div>
    </>
  )
}

function SidebarItem({ icon: Icon, label, active }: { icon: any, label: string, active?: boolean }) {
    return (
        <button className={cn(
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
