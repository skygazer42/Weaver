'use client'

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquarePlus,
  MessageSquare,
  History,
  Settings,
  Trash2
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface SidebarProps {
  isCollapsed: boolean
  onToggle: () => void
}

interface Conversation {
  id: string
  title: string
  timestamp: string
}

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([
    { id: '1', title: '研究 AI 框架对比', timestamp: '2 hours ago' },
    { id: '2', title: 'Python 最佳实践', timestamp: 'Yesterday' },
    { id: '3', title: 'Next.js 性能优化', timestamp: '2 days ago' },
  ])

  const [activeConversation, setActiveConversation] = useState<string>('1')

  const handleNewChat = () => {
    const newConv: Conversation = {
      id: Date.now().toString(),
      title: '新对话',
      timestamp: 'Just now'
    }
    setConversations([newConv, ...conversations])
    setActiveConversation(newConv.id)
  }

  const handleDeleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setConversations(conversations.filter(conv => conv.id !== id))
    if (activeConversation === id && conversations.length > 1) {
      setActiveConversation(conversations.find(c => c.id !== id)?.id || '')
    }
  }

  return (
    <div
      className={cn(
        'relative flex h-full flex-col border-r bg-muted/10 transition-all duration-300',
        isCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo & Toggle */}
      <div className="flex items-center justify-between border-b p-4">
        {!isCollapsed && (
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <span className="text-lg font-bold">M</span>
            </div>
            <span className="text-lg font-semibold">Manus</span>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          className={cn(isCollapsed && 'mx-auto')}
        >
          {isCollapsed ? (
            <PanelLeftOpen className="h-5 w-5" />
          ) : (
            <PanelLeftClose className="h-5 w-5" />
          )}
        </Button>
      </div>

      {/* New Chat Button */}
      <div className="p-3">
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={handleNewChat}
        >
          <MessageSquarePlus className="h-5 w-5" />
          {!isCollapsed && <span>新对话</span>}
        </Button>
      </div>

      {/* Conversations List */}
      {!isCollapsed && (
        <ScrollArea className="flex-1 px-3">
          <div className="space-y-1">
            <div className="mb-2 px-2 text-xs font-semibold text-muted-foreground">
              历史对话
            </div>
            {conversations.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  'group relative flex cursor-pointer items-center gap-2 rounded-lg p-3 hover:bg-accent',
                  activeConversation === conv.id && 'bg-accent'
                )}
                onClick={() => setActiveConversation(conv.id)}
              >
                <MessageSquare className="h-4 w-4 flex-shrink-0" />
                <div className="flex-1 overflow-hidden">
                  <div className="truncate text-sm font-medium">
                    {conv.title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {conv.timestamp}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 opacity-0 group-hover:opacity-100"
                  onClick={(e) => handleDeleteConversation(conv.id, e)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}

      {/* Bottom Actions */}
      {!isCollapsed && (
        <div className="border-t p-3 space-y-1">
          <Button
            variant="ghost"
            className="w-full justify-start gap-2"
            size="sm"
          >
            <History className="h-4 w-4" />
            <span className="text-sm">历史记录</span>
          </Button>
          <Button
            variant="ghost"
            className="w-full justify-start gap-2"
            size="sm"
          >
            <Settings className="h-4 w-4" />
            <span className="text-sm">设置</span>
          </Button>
        </div>
      )}

      {isCollapsed && (
        <div className="border-t p-3 space-y-2">
          <Button variant="ghost" size="icon" className="w-full">
            <History className="h-5 w-5" />
          </Button>
          <Button variant="ghost" size="icon" className="w-full">
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      )}
    </div>
  )
}
