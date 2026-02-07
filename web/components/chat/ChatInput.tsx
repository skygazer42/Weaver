'use client'

import React, { useRef, useEffect, useState, useCallback, memo } from 'react'
import dynamic from 'next/dynamic'
import { Button } from '@/components/ui/button'
import { Send, Paperclip } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { createFilePreview } from '@/lib/file-utils'
import { ModeSelector } from './input/ModeSelector'
import { AttachmentPreview } from './input/AttachmentPreview'
import { getCommandTemplate } from './input/command-templates'

const CommandPalette = dynamic(
  () => import('./input/CommandPalette').then((mod) => ({ default: mod.CommandPalette })),
  { ssr: false },
)

const AudioControls = dynamic(
  () => import('./input/AudioControls').then((mod) => ({ default: mod.AudioControls })),
  { ssr: false },
)

interface ChatInputProps {
  input: string
  setInput: React.Dispatch<React.SetStateAction<string>>
  attachments: File[]
  setAttachments: (files: File[]) => void
  onSubmit: (e: React.FormEvent) => void
  isLoading: boolean
  onStop: () => void
  searchMode: string
  setSearchMode: (mode: string) => void
}

interface AttachmentPreviewItem {
  file: File
  previewUrl: string
  revoke: () => void
}

export const ChatInput = memo(function ChatInput({
  input,
  setInput,
  attachments,
  setAttachments,
  onSubmit,
  isLoading,
  onStop,
  searchMode,
  setSearchMode
}: ChatInputProps) {
  const { t } = useI18n()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isFocused, setIsFocused] = useState(false)
  const [showCommandMenu, setShowCommandMenu] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [previews, setPreviews] = useState<AttachmentPreviewItem[]>([])
  const previewMapRef = useRef<Map<File, AttachmentPreviewItem>>(new Map())

  // Manage attachment previews
  useEffect(() => {
    const map = previewMapRef.current
    const attachmentSet = new Set(attachments)
    const nextPreviews: AttachmentPreviewItem[] = []

    for (const file of attachments) {
      const existing = map.get(file)
      if (existing) {
        nextPreviews.push(existing)
        continue
      }

      const { url, revoke } = createFilePreview(file)
      const created = { file, previewUrl: url, revoke }
      map.set(file, created)
      nextPreviews.push(created)
    }

    for (const [file, preview] of map.entries()) {
      if (!attachmentSet.has(file)) {
        preview.revoke()
        map.delete(file)
      }
    }

    setPreviews(nextPreviews)
  }, [attachments])

  // Cleanup on unmount
  useEffect(() => {
    const previewMap = previewMapRef.current
    return () => {
      for (const preview of previewMap.values()) {
        preview.revoke()
      }
      previewMap.clear()
    }
  }, [])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'inherit'
      const scrollHeight = textareaRef.current.scrollHeight
      textareaRef.current.style.height = `${Math.min(Math.max(scrollHeight, 56), 200)}px`
    }
  }, [input])

  // Focus textarea when not loading
  useEffect(() => {
    if (!isLoading) {
      textareaRef.current?.focus()
    }
  }, [isLoading])

  // Event handlers with useCallback
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setAttachments([...attachments, ...Array.from(e.target.files)])
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [attachments, setAttachments])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    if (e.dataTransfer.files) {
      setAttachments([...attachments, ...Array.from(e.dataTransfer.files)])
    }
  }, [attachments, setAttachments])

  const removeAttachment = useCallback((index: number) => {
    setAttachments(attachments.filter((_, i) => i !== index))
  }, [attachments, setAttachments])

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    setInput(val)
    if (val === '/') setShowCommandMenu(true)
    else if (showCommandMenu && !val.startsWith('/')) setShowCommandMenu(false)
  }, [setInput, showCommandMenu])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !showCommandMenu) {
      e.preventDefault()
      onSubmit(e)
    }
    if (e.key === 'Escape') {
      setShowCommandMenu(false)
    }
  }, [onSubmit, showCommandMenu])

  const handleCommandSelect = useCallback((cmd: string) => {
    // Mode changes
    if (cmd === 'direct') setSearchMode('')
    else if (['agent', 'ultra', 'web', 'deep', 'deep_agent'].includes(cmd)) setSearchMode(cmd)

    // Special actions
    if (cmd === 'clear') window.location.reload()

    // Template insertion
    const template = getCommandTemplate(cmd)
    if (template) {
      setInput(template)
    } else {
      setInput('')
    }

    setShowCommandMenu(false)
    textareaRef.current?.focus()
  }, [setInput, setSearchMode])

  const handleTranscript = useCallback((text: string) => {
    setInput(prev => prev + (prev ? ' ' : '') + text)
  }, [setInput])

  const handleCommandClose = useCallback(() => {
    setShowCommandMenu(false)
  }, [])

  const mcpLabel = searchMode === 'mcp' ? 'MCP...' : t('askAnything')

  return (
    <div className="relative z-20 mx-auto w-full max-w-5xl px-4 pb-6">
      <div className="flex flex-col gap-2">
        {/* Command Menu */}
        {showCommandMenu ? (
          <CommandPalette
            show={showCommandMenu}
            onSelect={handleCommandSelect}
            onClose={handleCommandClose}
          />
        ) : null}

        {/* Mode Tabs */}
        <ModeSelector searchMode={searchMode} onModeChange={setSearchMode} />

        {/* Input Container */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            "relative group rounded-3xl border bg-background shadow-lg shadow-black/5 transition-all duration-300 overflow-hidden",
            isFocused ? "ring-2 ring-primary/20 border-primary shadow-xl shadow-primary/5 scale-[1.005]" : "border-border/50 hover:border-primary/30",
            isDragging ? "ring-2 ring-primary border-primary bg-primary/5" : "",
            isLoading && "opacity-80"
          )}
        >
          {/* Drag Overlay */}
          {isDragging && (
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
              <div className="text-primary font-medium flex flex-col items-center gap-2">
                <div className="p-4 rounded-full bg-primary/10">
                  <Paperclip className="h-8 w-8" />
                </div>
                <span>{t('dropFilesHere')}</span>
              </div>
            </div>
          )}

          {/* File Input */}
          <div className="absolute top-3 left-3 flex gap-1 z-10">
            <input
              type="file"
              multiple
              className="hidden"
              ref={fileInputRef}
              onChange={handleFileSelect}
              aria-label="Upload files"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-full transition-colors"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Attach files"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex flex-col w-full">
            {/* Attachments Preview */}
            <AttachmentPreview
              previews={previews.map(p => ({ file: p.file, previewUrl: p.previewUrl }))}
              onRemove={removeAttachment}
            />

            {/* Textarea */}
            <label htmlFor="chat-input" className="sr-only">
              Message input
            </label>
            <textarea
              id="chat-input"
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={mcpLabel}
              disabled={isLoading}
              rows={1}
              aria-describedby="chat-input-hint"
              className={cn(
                "w-full resize-none bg-transparent px-14 min-h-[56px] max-h-[200px] text-base focus:outline-none placeholder:text-muted-foreground/50 scrollbar-thin scrollbar-thumb-muted",
                attachments.length > 0 ? "pt-2 pb-4" : "py-4"
              )}
            />
            <span id="chat-input-hint" className="sr-only">
              Press Enter to send, Shift+Enter for new line. Type / for commands.
            </span>
          </div>

          {/* Action Buttons */}
          <div className="absolute bottom-3 right-3 flex items-center gap-2">
            {!isLoading && (
              <AudioControls onTranscript={handleTranscript} disabled={isLoading} />
            )}

            {isLoading ? (
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={onStop}
                className="h-8 w-8 hover:bg-destructive/10 hover:text-destructive rounded-full"
                aria-label="Stop generation"
              >
                <div className="h-2.5 w-2.5 bg-current rounded-sm animate-pulse" />
              </Button>
            ) : (
              <Button
                type="button"
                size="icon"
                onClick={(e) => onSubmit(e as any)}
                disabled={!input.trim() && attachments.length === 0}
                aria-label="Send message"
                className={cn(
                  "h-8 w-8 rounded-full transition-all duration-300 shadow-sm",
                  (input.trim() || attachments.length > 0)
                    ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-110"
                    : "bg-muted text-muted-foreground"
                )}
              >
                <Send className="h-4 w-4 ml-0.5" />
              </Button>
            )}
          </div>
        </div>

        {/* Footer hints */}
        <div className="flex justify-between px-4 text-[10px] text-muted-foreground opacity-60">
          <span><strong>/</strong> {t('forCommands')}</span>
          <span>{t('aiCanMakeMistakes')}</span>
        </div>
      </div>
    </div>
  )
})
