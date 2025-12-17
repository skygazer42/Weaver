'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Brain } from 'lucide-react'

interface HeaderProps {
  selectedModel: string
  onModelChange: (model: string) => void
}

export function Header({ selectedModel, onModelChange }: HeaderProps) {
  return (
    <div className="flex h-14 items-center justify-between border-b bg-background px-4">
      {/* Center Logo */}
      <div className="flex-1" />

      <div className="flex items-center gap-2">
        <Brain className="h-5 w-5 text-primary" />
        <span className="text-sm font-medium text-muted-foreground">
          AI Research Assistant
        </span>
      </div>

      <div className="flex flex-1 items-center justify-end gap-3">
        {/* Model Selector */}
        <Select value={selectedModel} onValueChange={onModelChange}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="选择模型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="gpt-4o">GPT-4o</SelectItem>
            <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
            <SelectItem value="o1-mini">o1-mini (推理)</SelectItem>
            <SelectItem value="o1-preview">o1-preview</SelectItem>
            <SelectItem value="claude-3.5-sonnet">Claude 3.5 Sonnet</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
