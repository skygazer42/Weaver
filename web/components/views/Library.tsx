'use client'

import React, { useState, useMemo } from 'react'
import { History, Plus } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { useChatHistory } from '@/hooks/useChatHistory'
import { useArtifacts } from '@/hooks/useArtifacts'
import { SessionItem } from '@/components/library/SessionItem'
import { ArtifactItem } from '@/components/library/ArtifactItem'
import { SearchInput } from '@/components/ui/search-input'
import { FilterGroup } from '@/components/ui/filter-group'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EditDialog } from '@/components/ui/edit-dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

type LibraryTab = 'all' | 'sessions' | 'artifacts' | 'pinned'

interface LibraryProps {
  workspaceId?: string
  chatHistory: ReturnType<typeof useChatHistory>
  onNewChat: () => void
  onSelectChat: (id: string) => void
  onDeleteChat: (id: string) => void
}

export function Library({ workspaceId, chatHistory, onNewChat, onSelectChat, onDeleteChat }: LibraryProps) {
  const { history, togglePin, renameSession, isHistoryLoading } = chatHistory
  const { artifacts, deleteArtifact, isLoading: isArtifactsLoading } = useArtifacts(workspaceId)

  const [activeTab, setActiveTab] = useState<LibraryTab>('all')
  const [searchQuery, setSearchQuery] = useState('')
  
  // Dialog States
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [deleteType, setDeleteType] = useState<'session' | 'artifact' | null>(null)
  const [editSession, setEditSession] = useState<{id: string, title: string} | null>(null)

  const filterOptions = [
    { label: 'All Items', value: 'all' },
    { label: 'Chats', value: 'sessions' },
    { label: 'Files', value: 'artifacts' },
    { label: 'Pinned', value: 'pinned' },
  ]

  const filteredItems = useMemo(() => {
    let combined: any[] = []
    
    if (activeTab === 'all' || activeTab === 'sessions' || activeTab === 'pinned') {
        const h = history.map(s => ({ ...s, libType: 'session' as const }))
        combined = [...combined, ...h]
    }
    
    if (activeTab === 'all' || activeTab === 'artifacts') {
        const a = artifacts.map(art => ({ ...art, libType: 'artifact' as const }))
        combined = [...combined, ...a]
    }

    if (activeTab === 'pinned') {
        combined = combined.filter(item => item.isPinned)
    }

    return combined
      .filter(item => {
        const titleMatch = item.title?.toLowerCase().includes(searchQuery.toLowerCase())
        const contentMatch = item.content?.toLowerCase().includes(searchQuery.toLowerCase())
        return titleMatch || contentMatch
      })
      .sort((a, b) => (b.updatedAt || b.createdAt) - (a.updatedAt || a.createdAt))
  }, [activeTab, searchQuery, history, artifacts])

  const handleDelete = () => {
    if (!deleteId || !deleteType) return
    if (deleteType === 'session') onDeleteChat(deleteId)
    else deleteArtifact(deleteId)
    setDeleteId(null)
  }

  const handleRename = (newTitle: string) => {
    if (editSession) {
      renameSession(editSession.id, newTitle)
      setEditSession(null)
    }
  }

  const isLoading = isHistoryLoading || isArtifactsLoading

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col gap-5 p-4 sm:p-6 lg:p-8">
        
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h1 className="text-xl font-semibold tracking-tight">Library</h1>
              <Badge variant="subtle" className="tabular-nums" aria-label={`${filteredItems.length} items`}>{filteredItems.length}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Manage your saved conversations and artifacts.
            </p>
          </div>
          <div className="flex items-center gap-2">
             <Button size="sm" onClick={onNewChat} className="shrink-0 gap-1.5">
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                New Chat
             </Button>
          </div>
        </div>

        {/* Controls */}
        <div className="shrink-0 border-b border-border/70 pb-4">
          <div className="flex flex-col items-start justify-between gap-3 xl:flex-row xl:items-center">
            <FilterGroup 
              options={filterOptions} 
              value={activeTab} 
              onChange={(v) => setActiveTab(v as LibraryTab)} 
            />
            <SearchInput 
              onSearch={setSearchQuery} 
              placeholder="Search in library..." 
              aria-label="Search in library"
              containerClassName="w-full xl:w-72"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0">
          <ScrollArea className="h-full pr-4">
            {isLoading ? (
              <div role="status" className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                Loading your library...
              </div>
            ) : filteredItems.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-10">
                {filteredItems.map((item) => (
                  item.libType === 'session' ? (
                    <SessionItem 
                      key={item.id} 
                      session={item} 
                      onSelect={onSelectChat}
                      onDelete={(id) => { setDeleteId(id); setDeleteType('session'); }}
                      onRename={(id) => setEditSession({ id, title: item.title })}
                      onTogglePin={togglePin}
                    />
                  ) : (
                    <ArtifactItem 
                      key={item.id} 
                      artifact={item}
                      onDelete={(id) => { setDeleteId(id); setDeleteType('artifact'); }}
                    />
                  )
                ))}
              </div>
            ) : (
              <div className="flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-border/80 bg-surface-subtle/60 p-5 text-center">
                <History className="mb-3 h-5 w-5 text-muted-foreground" aria-hidden="true" />
                <h3 className="text-sm font-semibold">No items found</h3>
                <p className="mt-1 max-w-xs break-words text-center text-sm text-muted-foreground">
                    {searchQuery ? `We couldn't find anything matching "${searchQuery}"` : "Your library is empty. Start a conversation to see it here."}
                </p>
              </div>
            )}
          </ScrollArea>
        </div>
      </div>

      {/* Dialogs */}
      <ConfirmDialog 
        open={!!deleteId} 
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Item"
        description="Are you sure you want to delete this? This action cannot be undone."
        onConfirm={handleDelete}
        variant="destructive"
      />

      {editSession && (
        <EditDialog 
          open={!!editSession}
          onOpenChange={(open) => !open && setEditSession(null)}
          title="Rename Session"
          label="Session Title"
          initialValue={editSession.title}
          onSave={handleRename}
        />
      )}
    </div>
  )
}
