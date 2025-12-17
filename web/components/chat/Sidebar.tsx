'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Plus, MessageSquare, Settings, ChevronLeft, ChevronRight, User } from 'lucide-react'

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
}

export function Sidebar({ isOpen, onToggle }: SidebarProps) {
  return (
    <div
      className={cn(
        "relative flex flex-col border-r bg-muted/10 transition-all duration-300",
        isOpen ? "w-64" : "w-0 overflow-hidden"
      )}
    >
      <div className="flex h-full flex-col p-4">
        {/* New Chat Button */}
        <Button 
          variant="outline" 
          className={cn("justify-start gap-2 mb-4", !isOpen && "px-2")}
          onClick={() => window.location.reload()} // Simple reset for now
        >
          <Plus className="h-4 w-4" />
          <span className={cn("truncate", !isOpen && "hidden")}>New Chat</span>
        </Button>

        {/* Navigation / History */}
        <div className="flex-1 overflow-y-auto space-y-2">
          <div className="text-xs font-medium text-muted-foreground mb-2 px-2">History</div>
          {[1, 2, 3].map((i) => (
            <Button
              key={i}
              variant="ghost"
              className="w-full justify-start gap-2 text-sm font-normal"
            >
              <MessageSquare className="h-4 w-4" />
              <span className="truncate">Previous Research {i}</span>
            </Button>
          ))}
        </div>

        {/* User / Settings */}
        <div className="mt-auto pt-4 border-t space-y-2">
          <Button variant="ghost" className="w-full justify-start gap-2">
            <User className="h-4 w-4" />
            <span>User Profile</span>
          </Button>
          <Button variant="ghost" className="w-full justify-start gap-2">
            <Settings className="h-4 w-4" />
            <span>Settings</span>
          </Button>
        </div>
      </div>
    </div>
  )
}
