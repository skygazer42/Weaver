'use client'

import React, { useState, useMemo, useCallback } from 'react'
import { FolderOpen, History, FileCode, Star, Trash2 } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { VirtuosoGrid } from 'react-virtuoso'
import { useChatHistory } from '@/hooks/useChatHistory'
import { useArtifacts } from '@/hooks/useArtifacts'
import { SessionItem } from '@/components/library/SessionItem'
import { ArtifactItem } from '@/components/library/ArtifactItem'
import { SearchInput } from '@/components/ui/search-input'
import { FilterGroup } from '@/components/ui/filter-group'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EditDialog } from '@/components/ui/edit-dialog'
import { Button } from '@/components/ui/button'
import { useRouter } from 'next/navigation'

type LibraryTab = 'all' | 'sessions' | 'artifacts' | 'pinned'

export function Library() {
  const router = useRouter()
  const { history, deleteSession, togglePin, renameSession, isHistoryLoading } = useChatHistory()
  const { artifacts, deleteArtifact, isLoading: isArtifactsLoading } = useArtifacts()

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
    if (deleteType === 'session') deleteSession(deleteId)
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
    <div className="flex-1 h-full overflow-hidden flex flex-col bg-background">
      <div className="max-w-6xl mx-auto w-full h-full flex flex-col p-6 md:p-10 gap-8">

        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <FolderOpen className="h-8 w-8 text-primary" />
              Library
            </h1>
            <p className="text-muted-foreground mt-2 text-lg">
              Manage your saved conversations and artifacts.
            </p>
          </div>
          <div className="flex items-center gap-2">
             <Button variant="outline" size="sm" onClick={() => router.push('/')}>
                New Chat
             </Button>
          </div>
        </div>

        {/* Controls */}
        <div className="space-y-4">
          <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
            <FilterGroup
              options={filterOptions}
              value={activeTab}
              onChange={(v) => setActiveTab(v as LibraryTab)}
            />
            <SearchInput
              onSearch={setSearchQuery}
              placeholder="Search in library..."
              className="w-full md:w-80"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0">
            {isLoading ? (
              <div className="flex items-center justify-center h-40 text-muted-foreground">
                Loading your library...
              </div>
            ) : filteredItems.length > 0 ? (
              filteredItems.length > 30 ? (
                // Virtualized grid for large collections
                <VirtuosoGrid
                  style={{ height: '100%' }}
                  totalCount={filteredItems.length}
                  listClassName="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-10 pr-4"
                  itemContent={(index) => {
                    const item = filteredItems[index]
                    return item.libType === 'session' ? (
                      <SessionItem
                        key={item.id}
                        session={item}
                        onSelect={(id) => router.push(`/?session=${id}`)}
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
                  }}
                />
              ) : (
                // Standard rendering for small collections
                <ScrollArea className="h-full pr-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-10">
                    {filteredItems.map((item) => (
                      item.libType === 'session' ? (
                        <SessionItem
                          key={item.id}
                          session={item}
                          onSelect={(id) => router.push(`/?session=${id}`)}
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
                </ScrollArea>
              )
            ) : (
              <div className="flex flex-col items-center justify-center h-80 border-2 border-dashed rounded-3xl bg-muted/30">
                <div className="h-16 w-16 bg-muted rounded-full flex items-center justify-center mb-4">
                    <History className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-xl font-semibold">No items found</h3>
                <p className="text-muted-foreground mt-1 text-center max-w-xs">
                    {searchQuery ? `We couldn't find anything matching "${searchQuery}"` : "Your library is empty. Start a conversation to see it here."}
                </p>
              </div>
            )}
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
