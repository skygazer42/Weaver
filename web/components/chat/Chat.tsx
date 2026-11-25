'use client'

import React, { useRef, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { MessageItem } from './MessageItem'
import { ResearchStudioPanel, ResearchStudioRail } from './ResearchStudioPanel'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { EmptyState } from './EmptyState'
import { ChatInput } from './ChatInput'
import { Loader2, ArrowDown, GitFork, PanelRightClose, PanelRightOpen, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { ChatRun, Message, type RunStatus } from '@/types/chat'
import { useI18n } from '@/lib/i18n/i18n-context'
import { STORAGE_KEYS, DEFAULT_MODEL } from '@/lib/constants'
import { StorageService } from '@/lib/storage-service'
import { useChatHistory } from '@/hooks/useChatHistory'
import { useStoredPreference } from '@/hooks/useStoredPreference'
import { usePublicModels } from '@/hooks/usePublicModels'
import { cancelRun, useChatStream } from '@/hooks/useChatStream'
import { filesToImageAttachments } from '@/lib/file-utils'
import { composePromptWithResearchPlan, extractResearchStudio, resolveStudioCitation, resolveStudioTab, type BrowserDockMode, type StudioTab } from '@/lib/researchStudio'
import type { Workspace } from '@/lib/workspace'
import { Discover } from '@/components/views/Discover'
import { Library } from '@/components/views/Library'
import { SettingsDialog } from '@/components/settings/SettingsDialog'
import { FloatingBrowserViewer } from './BrowserViewer'

const studioDesktopQuery = '(min-width: 1280px)'
function subscribeToStudioViewport(notify: () => void) {
  const media = window.matchMedia(studioDesktopQuery)
  media.addEventListener('change', notify)
  return () => media.removeEventListener('change', notify)
}
const isDesktopStudioViewport = () => window.matchMedia(studioDesktopQuery).matches
const isServerStudioViewport = () => false

export function Chat({ project }: { project?: Pick<Workspace, 'id' | 'name'> }) {
  const { t, language } = useI18n()
  const workspaceId = project?.id
  const initialMode = project ? 'agent' : ''
  // UI State
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [composerFocusSignal, setComposerFocusSignal] = useState(0)
  const [selectedModel, setSelectedModel] = useStoredPreference(STORAGE_KEYS.MODEL, DEFAULT_MODEL)
  const [reasoningModel, setReasoningModel] = useStoredPreference(STORAGE_KEYS.REASONING_MODEL, '')
  const { models: publicModels } = usePublicModels()
  const [searchMode, setSearchMode] = useState(initialMode)
  const [showScrollButton, setShowScrollButton] = useState(false)
  const [showMobileStudio, setShowMobileStudio] = useState(false)
  const [isStudioOpen, setIsStudioOpen] = useState(true)
  const [studioTabs, setStudioTabs] = useState<Record<string, StudioTab>>({})
  const isDesktop = useSyncExternalStore(subscribeToStudioViewport, isDesktopStudioViewport, isServerStudioViewport)
  if (isDesktop && showMobileStudio) setShowMobileStudio(false)
  const [showSettings, setShowSettings] = useState(false)
  const [settingsSection, setSettingsSection] = useState<'general' | 'mcp'>('general')
  const [showBrowserViewer, setShowBrowserViewer] = useState(false)
  const [browserDockMode, setBrowserDockMode] = useState<BrowserDockMode>('docked')
  const [citation, setCitation] = useState<{ session: string; index: number }>()

  const [currentView, setCurrentView] = useState('dashboard') // 'dashboard' | 'discover' | 'library'
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)

  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<File[]>([])
  const [researchPlan, setResearchPlan] = useState<string[]>([])
  const [planReset, setPlanReset] = useState(0)
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const studioToggle = useRef<HTMLButtonElement>(null)
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const lastAtBottom = useRef<boolean | null>(null)
  const [restoredSession, setRestoredSession] = useState<{
    id: string
    run: ChatRun
    messages: Message[]
    missingHistory: boolean
  } | false | null>(null)
  const submissionRef = useRef<symbol | null>(null)

  const {
    messages,
    setMessages,
    isLoading,
    isRunSnapshot,
    connectionLost,
    isDeciding,
    isStopping,
    currentStatus,
    setCurrentStatus,
    pendingInterrupt,
    setPendingInterrupt,
    threadId,
    setThreadId,
    processChat,
    resumeRun,
    detachChat,
    handleStop,
    decideInterrupt,
  } = useChatStream({ selectedModel, reasoningModel, searchMode, workspaceId })

  useEffect(() => {
    if (!publicModels?.options.length) return
    const allowlist = new Set(publicModels.options)
    if (!allowlist.has(selectedModel)) {
      setSelectedModel(allowlist.has(publicModels.default) ? publicModels.default : publicModels.options[0])
    }
    if (reasoningModel && !allowlist.has(reasoningModel)) setReasoningModel('')
  }, [publicModels, selectedModel, setSelectedModel, reasoningModel, setReasoningModel])

  const chatHistory = useChatHistory(workspaceId)
  const {
    history,
    isHistoryLoading,
    saveToHistory,
    loadSession,
    deleteSession,
    clearHistory,
    togglePin,
    renameSession
  } = chatHistory

  if (!isHistoryLoading && restoredSession === null) {
    const id = StorageService.getRecentRunSession(workspaceId)
      || history.find((item) => StorageService.getRun(item.id, workspaceId))?.id
    const run = id ? StorageService.getRun(id, workspaceId) : null
    const saved = id ? StorageService.getSessionMessages<Message>(id, workspaceId) : []
    if (id && run && saved.length > 0) {
      setRestoredSession({ id, run, messages: saved, missingHistory: !history.some((item) => item.id === id) })
      setMessages(saved)
      setCurrentSessionId(id)
      setSearchMode(run.searchMode)
    } else {
      setRestoredSession(false)
    }
  }

  useEffect(() => {
    if (!restoredSession) return
    const { id, run, messages: saved, missingHistory } = restoredSession
    if (missingHistory) saveToHistory(saved, id, run.searchMode)
    void resumeRun(id, run, saved)
  }, [restoredSession, resumeRun, saveToHistory])

  const runStatus = messages.at(-1)?.runStatus
  const studio = useMemo(() => extractResearchStudio(messages, language), [messages, language])
  const hasTree = Boolean(studio.tree || studio.mindMap)
  const hasArtifacts = studio.artifacts.length > 0
  const hasSources = studio.sources.length > 0 || studio.media.length > 0
  const hasStudioContent = currentView === 'dashboard' && (hasTree || hasArtifacts || hasSources || Boolean(threadId))
  const studioSession = currentSessionId ?? ''
  const savedTab = studioTabs[studioSession]
  const activeTab = resolveStudioTab({ hasTree, hasArtifacts, hasSources, isResearchActive: studio.isResearchActive },
    savedTab === 'live' && !threadId ? undefined : savedTab)
  const onStudioTabChange = (tab: StudioTab) => setStudioTabs(previous => ({ ...previous, [studioSession]: tab }))
  const openStudioTab = (tab: StudioTab) => {
    onStudioTabChange(tab)
    if (isDesktop) setIsStudioOpen(true)
    else setShowMobileStudio(true)
  }
  const dockBrowser = () => {
    setBrowserDockMode('docked')
    setShowBrowserViewer(false)
    openStudioTab('live')
  }
  const undockBrowser = () => {
    setBrowserDockMode('floating')
    setShowBrowserViewer(true)
    setShowMobileStudio(false)
  }
  const isDockedLiveOpen = activeTab === 'live' && (isDesktop ? isStudioOpen : showMobileStudio)
  const toggleBrowser = () => {
    if (browserDockMode === 'floating') setShowBrowserViewer(open => !open)
    else if (isDockedLiveOpen) document.querySelector<HTMLButtonElement>('[data-studio-tab="live"]')?.focus()
    else openStudioTab('live')
  }
  const studioProps = {
    studio, activeTab, onTabChange: onStudioTabChange, threadId, browserDockMode,
    onDock: dockBrowser, onUndock: undockBrowser,
    citation: activeTab === 'sources' && citation?.session === studioSession ? citation : undefined,
  }
  function openCitation(message: Message, index: number) {
    const source = resolveStudioCitation(index, message.sources, studio.sources)
    if (!source) return
    setCitation({ session: studioSession, index: source.index })
    openStudioTab('sources')
  }
  function resetResearchPlan() {
    setResearchPlan([])
    setPlanReset(value => value + 1)
  }
  const isWideLayout = !sidebarOpen && !(hasStudioContent && (isDesktop ? isStudioOpen : showMobileStudio))
  const columnWidthClass = cn(
    'mx-auto w-full transition-[max-width] duration-200 ease-out motion-reduce:transition-none',
    isWideLayout ? 'max-w-4xl' : 'max-w-3xl'
  )
  const activeRun = currentSessionId ? StorageService.getRun(currentSessionId, workspaceId) : null
  const approvalPrompts = pendingInterrupt?.prompts ?? (pendingInterrupt ? [pendingInterrupt] : [])

  // Auto-save messages when they update during streaming or after approval
  useEffect(() => {
    if (messages.length > 0 && currentSessionId && !isLoading && !isRunSnapshot) {
      saveToHistory(messages, currentSessionId)
    }
  }, [messages, currentSessionId, isLoading, isRunSnapshot, saveToHistory])

  // Auto-scroll logic handled by Virtuoso's followOutput, 
  // but we can add specific triggers if needed.

  const handleNewChat = () => {
      detachChat()
      submissionRef.current = null
      
      setCurrentView('dashboard') // Switch back to chat view
      setCurrentSessionId(null)
      
      // Reset state
      setMessages([])
      setCurrentStatus('')
      setInput('')
      setAttachments([])
      resetResearchPlan()
      setShowBrowserViewer(false)
      setShowMobileStudio(false)
      setCitation(undefined)
      setThreadId(null)
      setPendingInterrupt(null)
      setSearchMode(initialMode)
  }

  const stopSavedRun = (id: string) => {
    const run = StorageService.getRun(id, workspaceId)
    if (!run) return false
    void cancelRun(run.id).catch((error) => console.error('Failed to stop run', error))
    return true
  }

  const handleDeleteChat = (id: string) => {
      const stoppedRun = stopSavedRun(id)
      deleteSession(id)
      if (currentSessionId === id) {
          if (!stoppedRun) void handleStop()
          handleNewChat()
      }
  }

  const handleClearHistory = () => {
      const ids = new Set(history.map((session) => session.id))
      if (currentSessionId) ids.add(currentSessionId)
      for (const id of ids) stopSavedRun(id)
      if (!isRunSnapshot) void handleStop()
      clearHistory()
      handleNewChat() // Reset current view as well
  }

  const handleChatSelect = (id: string) => {
    detachChat()
    submissionRef.current = null
    // Save current chat if not empty
    if (messages.length > 0 && !isRunSnapshot) {
        saveToHistory(messages, currentSessionId || undefined)
    }
    
    // Load new session
    const loadedMessages = loadSession(id)
    if (loadedMessages) {
      setMessages(loadedMessages)
      setCurrentSessionId(id)
      setCurrentView('dashboard') // Ensure we are on the chat view
      // Reset other state
      setCurrentStatus('')
      setInput('')
      setAttachments([])
      resetResearchPlan()
      setShowBrowserViewer(false)
      setShowMobileStudio(false)
      setCitation(undefined)
      setThreadId(null)
      setPendingInterrupt(null)
      const run = StorageService.getRun(id, workspaceId)
      setSearchMode(run?.searchMode ?? history.find((item) => item.id === id)?.searchMode ?? initialMode)
      if (run) void resumeRun(id, run, loadedMessages)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if ((!input.trim() && attachments.length === 0) || isLoading || pendingInterrupt || submissionRef.current) return
    if (currentSessionId && activeRun) {
      await resumeRun(currentSessionId, activeRun, messages)
      return
    }

    const submission = Symbol()
    submissionRef.current = submission
    try {
      const imagePayloads = await filesToImageAttachments(attachments)
      if (submissionRef.current !== submission) return

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: composePromptWithResearchPlan(input.trim(), searchMode === 'deep' || searchMode === 'ultra' ? researchPlan : [], language),
        attachments: imagePayloads
      }

      const newHistory = [...messages, userMessage]
      setMessages(newHistory)
      setInput('')
      setAttachments([])
      resetResearchPlan()
    
      const id = saveToHistory(newHistory, currentSessionId || undefined, searchMode)
      if (id) setCurrentSessionId(id)
      await processChat(newHistory, imagePayloads, id || undefined)
    } finally {
      if (submissionRef.current === submission) submissionRef.current = null
    }
  }

  const handleEditMessage = async (id: string, newContent: string) => {
      if (isLoading || activeRun || pendingInterrupt) return
      const index = messages.findIndex(m => m.id === id)
      if (index === -1) return

      const previousMessages = messages.slice(0, index)
      const updatedMessage: Message = {
          ...messages[index],
          content: newContent
      }

      const newHistory = [...previousMessages, updatedMessage]
      setMessages(newHistory)

      if (updatedMessage.role === 'user') {
          const session = saveToHistory(newHistory, currentSessionId || undefined, searchMode)
          if (session) setCurrentSessionId(session)
          await processChat(newHistory, updatedMessage.attachments, session || undefined)
      }
  }

  const retryResearch = () => {
    if (!currentSessionId || isLoading || activeRun) return
    const index = messages.findLastIndex((message) => message.role === 'user')
    if (index < 0) return
    const previousMessages = messages.slice(0, index + 1)
    const mode = history.find((session) => session.id === currentSessionId)?.searchMode ?? searchMode
    setSearchMode(mode)
    setMessages(previousMessages)
    saveToHistory(previousMessages, currentSessionId, mode)
    void processChat(previousMessages, messages[index].attachments, currentSessionId, mode)
  }

  const runStatusLabels: Record<RunStatus, string> = {
    queued: t('runStatusQueued'),
    running: t('runStatusRunning'),
    awaiting_approval: t('runStatusAwaitingApproval'),
    completed: t('runStatusCompleted'),
    failed: t('runStatusFailed'),
    cancelled: t('runStatusCancelled'),
    insufficient_evidence: t('runStatusInsufficientEvidence'),
  }

  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'b') {
        event.preventDefault()
        setSidebarOpen((open) => !open)
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [])

  const handleStarterClick = (text: string, mode: string) => {
      setInput(text)
      setSearchMode(mode)
      setComposerFocusSignal((count) => count + 1)
  }

  const handleAtBottomChange = (atBottom: boolean) => {
      // Prevent state churn loops from repeated identical callbacks
      if (lastAtBottom.current === atBottom) return
      lastAtBottom.current = atBottom
      setShowScrollButton(!atBottom)
  }

  const scrollToBottom = () => {
      const idx = messages.length - 1
      if (idx >= 0) {
          virtuosoRef.current?.scrollToIndex({
              index: idx,
              align: 'end',
              behavior: 'smooth'
          })
      }
  }

  // Render Content based on View
  const renderContent = () => {
      if (currentView === 'discover') return <Discover />
      if (currentView === 'library') {
        return <Library workspaceId={workspaceId} chatHistory={chatHistory} onNewChat={handleNewChat} onSelectChat={handleChatSelect} onDeleteChat={handleDeleteChat} />
      }
      
      // Default: Dashboard/Chat
      return (
        <div className="flex-1 flex flex-col min-h-0">
          {messages.length === 0 ? (
            <div className="h-full w-full overflow-y-auto">
               <EmptyState
                  onStarterClick={handleStarterClick}
                  wide={isWideLayout}
               />
            </div>
          ) : (
            <Virtuoso
                ref={virtuosoRef}
                data={messages}
                followOutput="auto"
                atBottomStateChange={handleAtBottomChange}
                className="scrollbar-thin scrollbar-thumb-muted/20"
                itemContent={(index, message) => (
                    <div className={cn(columnWidthClass, 'px-4 sm:px-6')}>
                        <MessageItem key={message.id} message={message} onEdit={handleEditMessage} workspaceId={workspaceId}
                          sources={studio.sources} onCitationClick={message.role === 'assistant' ? index => openCitation(message, index) : undefined} />
                    </div>
                )}
            />
          )}
        </div>
      )
  }

  return (
    <Dialog open={!isDesktop && hasStudioContent && showMobileStudio} onOpenChange={setShowMobileStudio}>
    <div className="flex h-dvh w-full overflow-hidden bg-background font-sans text-foreground selection:bg-primary/20">
      {/* Sidebar */}
      <Sidebar 
        isOpen={sidebarOpen} 
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onNewChat={handleNewChat}
        onSelectChat={handleChatSelect}
        onDeleteChat={handleDeleteChat}
        onTogglePin={togglePin}
        onRenameChat={renameSession}
        onClearHistory={handleClearHistory}
        onOpenSettings={() => { setSettingsSection('general'); setShowSettings(true) }}
        activeView={currentView}
        activeSessionId={currentSessionId}
        onViewChange={setCurrentView}
        history={history}
        isLoading={isHistoryLoading}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Header */}
        <Header 
          project={project}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          onNewChat={handleNewChat}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          reasoningModel={reasoningModel}
          onReasoningModelChange={setReasoningModel}
          onOpenSettings={() => { setSettingsSection('general'); setShowSettings(true) }}
          hasStudioContent={hasStudioContent}
          isInitializing={isHistoryLoading}
          showBrowserToggle={currentView === 'dashboard' && Boolean(threadId)}
          isBrowserOpen={browserDockMode === 'docked' ? isDockedLiveOpen : showBrowserViewer}
          onToggleBrowser={toggleBrowser}
        />

        {/* Dynamic Content Area */}
        <div className="relative flex min-h-0 flex-1 flex-col">
          {renderContent()}
          {currentView === 'dashboard' && threadId && browserDockMode === 'floating' && showBrowserViewer && (
            <FloatingBrowserViewer
              threadId={threadId}
              defaultExpanded={true}
              alwaysShow={true}
              mode="stream"
              defaultPosition="bottom-left"
              onClose={() => setShowBrowserViewer(false)}
              onDock={dockBrowser}
            />
          )}
        </div>

        <SettingsDialog 
            open={showSettings} 
            initialSection={settingsSection}
            onOpenChange={setShowSettings} 
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            reasoningModel={reasoningModel}
            onReasoningModelChange={setReasoningModel}
        />

        {/* Chat-specific overlays (Scroll button, Interrupts) - only show in dashboard view */}
        {currentView === 'dashboard' && (
           <>
                {/* Scroll To Bottom Button */}
                <div className={cn("absolute bottom-44 right-5 z-30 transition-[opacity,transform] duration-150", showScrollButton ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-2 opacity-0")} inert={!showScrollButton}>
                    <Button type="button" variant="outline" size="icon" aria-label={t('scrollToLatest')} className="rounded-lg border-border bg-card shadow-elevated hover:bg-accent" onClick={() => scrollToBottom()}>
                        <ArrowDown className="h-4 w-4" />
                    </Button>
                </div>

                {(runStatus || currentStatus || isStopping) && (
                  <div className={cn(columnWidthClass, 'flex flex-wrap items-center gap-2 border-t border-border/70 px-4 py-2.5 text-xs text-muted-foreground sm:px-6')}>
                    {isLoading ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin text-primary" /> : (
                      <span aria-hidden="true" className={cn('h-1.5 w-1.5 rounded-full', runStatus === 'completed' ? 'bg-success' : runStatus === 'failed' ? 'bg-destructive' : runStatus === 'awaiting_approval' || runStatus === 'insufficient_evidence' ? 'bg-warning' : 'bg-muted-foreground')} />
                    )}
                    {runStatus && <span role="status" aria-label="Run status" className="font-medium text-foreground">{runStatusLabels[runStatus]}</span>}
                    {isStopping ? <span>{t('stopping')}</span> : currentStatus && <span>{currentStatus}</span>}
                    {connectionLost && currentSessionId && activeRun && (
                      <Button size="sm" variant="outline" onClick={() => void resumeRun(currentSessionId, activeRun, messages)}>{t('reconnect')}</Button>
                    )}
                    {runStatus === 'insufficient_evidence' && !activeRun && (
                      <Button size="sm" variant="outline" onClick={retryResearch}>{t('retryResearch')}</Button>
                    )}
                  </div>
                )}

                {pendingInterrupt && (
                <div className={cn(columnWidthClass, 'px-4 sm:px-6')}>
                <section aria-labelledby="tool-approval-title" className="mb-2 flex max-h-[40vh] flex-col gap-3 overflow-auto rounded-lg border border-warning/40 bg-warning-surface p-4 text-foreground shadow-surface">
                    <h2 id="tool-approval-title" className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert aria-hidden="true" className="h-4 w-4 text-warning" />{t('toolApprovalRequired')}</h2>
                    {approvalPrompts.map((prompt, index) => (
                      <div key={index} className="space-y-2 text-sm leading-relaxed">
                        {prompt.message && <p>{prompt.message}</p>}
                        {(prompt.action_requests ?? prompt.tool_calls ?? []).map((action, actionIndex) => (
                          <div key={action.id ?? actionIndex} className="space-y-2 rounded-md border border-border/80 bg-card p-3">
                            <div className="font-mono text-xs font-medium">{action.name}</div>
                            {action.description && <p className="whitespace-pre-wrap text-xs text-muted-foreground">{action.description}</p>}
                            {action.args && (
                              <pre className="overflow-x-auto whitespace-pre-wrap break-words border-t border-border/70 pt-2 font-mono text-xs leading-6">{typeof action.args === 'string' ? action.args : JSON.stringify(action.args, null, 2)}</pre>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                    <div className="flex gap-2">
                    <Button size="sm" onClick={() => void decideInterrupt(true)} disabled={!threadId || isLoading || isStopping}>
                        {t('approveAndContinue')}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void decideInterrupt(false)} disabled={!threadId || isLoading || isStopping}>
                        {t('reject')}
                    </Button>
                    </div>
                </section>
                </div>
                )}
           </>
        )}

        {/* Input Area - Always visible or only in dashboard? Usually always visible in chat apps, but maybe hidden in Library? 
            For now, let's keep it visible only in Dashboard/Chat view to avoid confusion.
        */}
        {currentView === 'dashboard' && (
            <ChatInput 
            input={input}
            setInput={setInput}
            attachments={attachments}
            setAttachments={setAttachments}
            onSubmit={handleSubmit}
            researchPlan={researchPlan}
            setResearchPlan={setResearchPlan}
            planReset={planReset}
            isLoading={isLoading}
            awaitingApproval={Boolean(pendingInterrupt)}
            canStop={!isDeciding && (isLoading || (!!activeRun && (!!pendingInterrupt || connectionLost)))}
            isStopping={isStopping}
            onStop={handleStop}
            searchMode={searchMode}
            setSearchMode={setSearchMode}
            wide={isWideLayout}
            focusSignal={composerFocusSignal}
            onOpenSettings={() => { setSettingsSection('mcp'); setShowSettings(true) }}
            />
        )}
      </div>

      {hasStudioContent && isDesktop && (
        <aside aria-label={t('studioTitle')} className={cn(
            'relative z-20 hidden shrink-0 flex-col overflow-hidden border-l border-border bg-surface-subtle transition-[width] duration-200 motion-reduce:transition-none xl:flex',
            isStudioOpen ? 'w-[440px] 2xl:w-[480px]' : 'w-[50px]'
        )}>
          <Button ref={studioToggle} type="button" variant="ghost" size="icon" onClick={() => setIsStudioOpen(open => !open)}
            aria-expanded={isStudioOpen} aria-label={t(isStudioOpen ? 'studioCollapse' : 'studioOpen')}
            title={t(isStudioOpen ? 'studioCollapse' : 'studioOpen')} className="absolute right-[7px] top-2.5 z-10 text-muted-foreground">
            {isStudioOpen ? <PanelRightClose aria-hidden="true" className="size-4" /> : <PanelRightOpen aria-hidden="true" className="size-4" />}
          </Button>
          {isStudioOpen ? (
            <ResearchStudioPanel key={studioSession} {...studioProps} />
          ) : (
            <div className="pt-14">
              <ResearchStudioRail studio={studio} activeTab={activeTab} threadId={threadId} onTabChange={tab => {
                onStudioTabChange(tab)
                setIsStudioOpen(true)
                studioToggle.current?.focus()
              }} />
            </div>
          )}
        </aside>
      )}
      {hasStudioContent && !isDesktop && (
        <DialogContent aria-describedby={undefined} closeLabel={t('studioClose')}
          className="inset-0 flex h-dvh max-h-none w-full max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none border-0 bg-surface-subtle p-0">
          <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-card pl-4 pr-12">
            <GitFork aria-hidden="true" className="size-4 text-primary" />
            <DialogTitle className="text-sm">{t('studioTitle')}</DialogTitle>
          </div>
          <div className="min-h-0 flex-1">
            <ResearchStudioPanel key={studioSession} {...studioProps} showHeader={false} />
          </div>
        </DialogContent>
      )}
    </div>
    </Dialog>
  )
}
