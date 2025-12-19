'use client'

import React from 'react'
import { Compass, Sparkles, TrendingUp, Search, Plus, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useArtifacts } from '@/hooks/useArtifacts'
import { toast } from 'sonner'
import { useState } from 'react'

export function Discover() {
  const { saveArtifact } = useArtifacts()
  const [addedIds, setAddedIds] = useState<string[]>([])

  const featured = [
    { id: 't1', title: 'Market Trends 2025', desc: 'Deep dive into emerging tech markets', icon: TrendingUp, color: 'text-blue-500' },
    { id: 't2', title: 'Academic Research', desc: 'Find latest papers on LLM agents', icon: Search, color: 'text-purple-500' },
    { id: 't3', title: 'Creative Writing', desc: 'Story brainstorming with AI', icon: Sparkles, color: 'text-amber-500' },
  ]

  const handleAddTemplate = (item: any) => {
    saveArtifact({
        type: 'text',
        title: item.title,
        content: `Template for: ${item.title}\n\nDescription: ${item.desc}\n\n(This is a template you can use to start a new chat)`,
        tags: ['Template']
    })
    setAddedIds(prev => [...prev, item.id])
    toast.success(`${item.title} added to your library`)
    setTimeout(() => {
        setAddedIds(prev => prev.filter(id => id !== item.id))
    }, 2000)
  }

  return (
    <div className="flex-1 h-full overflow-y-auto p-6 md:p-10">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Compass className="h-8 w-8 text-primary" />
            Discover
          </h1>
          <p className="text-muted-foreground mt-2 text-lg">
            Explore curated research templates and community prompts.
          </p>
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search templates..." className="pl-10 h-12 text-base rounded-xl" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {featured.map((item, i) => (
            <div key={i} className="group relative p-6 rounded-2xl border bg-card hover:bg-muted/50 transition-all cursor-pointer shadow-sm hover:shadow-md">
              <div className={`h-12 w-12 rounded-xl bg-muted flex items-center justify-center mb-4 ${item.color} bg-opacity-10`}>
                <item.icon className={`h-6 w-6 ${item.color}`} />
              </div>
              <h3 className="font-semibold text-lg group-hover:text-primary transition-colors">{item.title}</h3>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{item.desc}</p>
              
              <Button 
                size="icon" 
                variant="secondary" 
                className="absolute top-4 right-4 h-8 w-8 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={(e) => {
                    e.stopPropagation()
                    handleAddTemplate(item)
                }}
              >
                {addedIds.includes(item.id) ? <Check className="h-4 w-4 text-green-500" /> : <Plus className="h-4 w-4" />}
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
