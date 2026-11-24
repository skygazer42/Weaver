'use client'

import { Sparkles, TrendingUp, Search, Plus, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SearchInput } from '@/components/ui/search-input'
import { useArtifacts } from '@/hooks/useArtifacts'
import { toast } from 'sonner'
import { useState } from 'react'

const featured = [
  { id: 't1', title: 'Market Trends 2025', desc: 'Deep dive into emerging tech markets', icon: TrendingUp, color: 'bg-info-surface text-info' },
  { id: 't2', title: 'Academic Research', desc: 'Find latest papers on LLM agents', icon: Search, color: 'bg-primary/10 text-primary' },
  { id: 't3', title: 'Creative Writing', desc: 'Story brainstorming with AI', icon: Sparkles, color: 'bg-warning-surface text-warning-foreground' },
]

export function Discover() {
  const { saveArtifact } = useArtifacts()
  const [addedIds, setAddedIds] = useState<string[]>([])
  const [searchQuery, setSearchQuery] = useState('')

  const query = searchQuery.trim().toLowerCase()
  const filteredTemplates = featured.filter(item => `${item.title} ${item.desc}`.toLowerCase().includes(query))

  const handleAddTemplate = (item: (typeof featured)[number]) => {
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
    <div className="h-full min-h-0 flex-1 overflow-y-auto bg-background p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Discover</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Research templates and prompts to start your next conversation.
          </p>
        </div>

        <SearchInput onSearch={setSearchQuery} placeholder="Search templates..." aria-label="Search templates" containerClassName="max-w-md" />

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredTemplates.map(item => (
            <div key={item.id} className="flex min-w-0 flex-col items-start rounded-lg border border-border/80 bg-card p-5 shadow-surface transition-colors hover:border-primary/40">
              <div className={`mb-4 flex h-9 w-9 items-center justify-center rounded-md ${item.color}`}>
                <item.icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <h2 className="text-base font-semibold tracking-tight">{item.title}</h2>
              <p className="mb-5 mt-1.5 flex-1 text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
              
              <Button 
                type="button"
                size="sm"
                variant="outline"
                className="gap-2"
                disabled={addedIds.includes(item.id)}
                aria-label={`${addedIds.includes(item.id) ? 'Added' : 'Add to library'}: ${item.title}`}
                onClick={() => handleAddTemplate(item)}
              >
                {addedIds.includes(item.id) ? <Check className="h-3.5 w-3.5 text-success" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
                {addedIds.includes(item.id) ? 'Added' : 'Add to library'}
              </Button>
            </div>
          ))}
        </div>
        {filteredTemplates.length === 0 && (
          <div role="status" className="rounded-lg border border-dashed border-border/80 bg-surface-subtle/60 px-5 py-12 text-center">
            <h2 className="text-sm font-semibold">No templates found</h2>
            <p className="mt-1 break-words text-sm text-muted-foreground">Try a different title or topic.</p>
          </div>
        )}
      </div>
    </div>
  )
}
