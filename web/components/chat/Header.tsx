'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { ChevronDown, PanelLeft } from 'lucide-react'

interface HeaderProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  selectedModel: string
  onModelChange: (model: string) => void
}

export function Header({ sidebarOpen, onToggleSidebar, selectedModel, onModelChange }: HeaderProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b px-4 bg-background">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={onToggleSidebar}>
          <PanelLeft className="h-5 w-5" />
        </Button>
        <span className="font-bold text-lg flex items-center gap-2">
          <span className="bg-primary text-primary-foreground rounded-md px-2 py-0.5 text-sm">M</span>
          Manus
        </span>
      </div>

      <div className="flex items-center gap-2">
         <div className="relative">
            <select 
              value={selectedModel}
              onChange={(e) => onModelChange(e.target.value)}
              className="h-9 w-[180px] rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-4o-mini">GPT-4o Mini</option>
                <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
            </select>
         </div>
      </div>
    </header>
  )
}