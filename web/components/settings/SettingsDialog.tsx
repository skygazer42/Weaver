'use client'

import React, { useState, useEffect, useMemo, useRef } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { Check, ChevronDown } from 'lucide-react'
import { McpServersPanel, type McpServersPanelHandle } from './McpServersPanel'
import { useMcpConfig } from '@/hooks/useMcpConfig'
import { usePublicModels } from '@/hooks/usePublicModels'
import { useStoredPreference } from '@/hooks/useStoredPreference'
import { getModelProviders } from '@/lib/models'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedModel: string
  onModelChange: (model: string) => void
  reasoningModel: string
  onReasoningModelChange: (model: string) => void
  initialSection?: 'general' | 'mcp'
}

const languages = [
  { id: 'en', name: 'English', nativeName: 'English' },
  { id: 'zh', name: 'Chinese', nativeName: '中文' },
  { id: 'ja', name: 'Japanese', nativeName: '日本語' },
  { id: 'ko', name: 'Korean', nativeName: '한국어' },
]

interface ApiKeys {
  [key: string]: string
}

export function SettingsDialog({ open, onOpenChange, selectedModel, onModelChange, reasoningModel, onReasoningModelChange, initialSection = 'general' }: SettingsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <SettingsDialogContent onOpenChange={onOpenChange} selectedModel={selectedModel} onModelChange={onModelChange} reasoningModel={reasoningModel} onReasoningModelChange={onReasoningModelChange} initialSection={initialSection} />}
    </Dialog>
  )
}

function SettingsDialogContent({ onOpenChange, selectedModel, onModelChange, reasoningModel, onReasoningModelChange, initialSection }: Omit<SettingsDialogProps, 'open'>) {
  const { language, setLanguage, t } = useI18n()
  const { models: publicModels } = usePublicModels()
  const [modelDraft, setTempModel] = useState<string | null>(null)
  const [reasoningModelDraft, setReasoningModelDraft] = useState<string | null>(null)
  const [modelRole, setModelRole] = useState<'primary' | 'reasoning'>('primary')
  const [modelQuery, setModelQuery] = useState('')
  const [languageDraft, setTempLanguage] = useState<typeof language | null>(null)
  const tempLanguage = languageDraft ?? language
  const [savedKeys, setSavedKeys] = useStoredPreference('weaver-api-keys', '{}')
  const storedKeys = useMemo<ApiKeys>(() => {
    try {
      return JSON.parse(savedKeys)
    } catch {
      return {}
    }
  }, [savedKeys])
  const [apiKeyDraft, setApiKeys] = useState<ApiKeys | null>(null)
  const apiKeys = apiKeyDraft ?? storedKeys
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null)

  const mcp = useMcpConfig()
  const mcpPanelRef = useRef<McpServersPanelHandle>(null)
  const mcpSectionRef = useRef<HTMLDivElement>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (initialSection !== 'mcp' || mcp.isLoading) return
    const frame = requestAnimationFrame(() => {
      mcpSectionRef.current?.focus({ preventScroll: true })
      mcpSectionRef.current?.scrollIntoView({ block: 'start' })
    })
    return () => cancelAnimationFrame(frame)
  }, [initialSection, mcp.isLoading])

  const modelProviders = getModelProviders(publicModels?.options)
  const allModels = modelProviders.flatMap(provider => provider.models)
  const query = modelQuery.trim().toLowerCase()
  const filteredProviders = modelProviders.map(provider => ({
    ...provider,
    models: provider.models.filter(model => `${provider.name} ${model.name} ${model.id}`.toLowerCase().includes(query)),
  })).filter(provider => provider.models.length > 0)
  const allowlist = publicModels?.options?.length ? new Set(publicModels.options) : null
  const requestedModel = modelDraft ?? selectedModel
  const tempModel = allowlist && !allowlist.has(requestedModel)
    ? (publicModels?.default && allowlist.has(publicModels.default) ? publicModels.default : publicModels!.options[0])
    : requestedModel
  const requestedReasoningModel = reasoningModelDraft ?? reasoningModel
  const tempReasoningModel = allowlist && requestedReasoningModel && !allowlist.has(requestedReasoningModel)
    ? '' : requestedReasoningModel
  const activeModel = modelRole === 'primary' ? tempModel : tempReasoningModel
  const primaryName = allModels.find(model => model.id === tempModel)?.name || tempModel
  const reasoningName = tempReasoningModel
    ? allModels.find(model => model.id === tempReasoningModel)?.name || tempReasoningModel
    : t('followPrimaryModel')

  const handleApiKeyChange = (provider: string, value: string) => {
    setApiKeys({
      ...apiKeys,
      [provider]: value
    })
  }

  const handleSave = async () => {
    if (!await mcpPanelRef.current?.save()) return
    onModelChange(tempModel)
    onReasoningModelChange(tempReasoningModel)
    setLanguage(tempLanguage)
    setSavedKeys(JSON.stringify(apiKeys))
    onOpenChange(false)
  }

  const handleCancel = () => {
    onOpenChange(false)
  }

  return (
      <DialogContent aria-describedby={undefined} onOpenAutoFocus={event => {
        if (initialSection === 'mcp') {
          event.preventDefault()
          mcpSectionRef.current?.focus({ preventScroll: true })
        }
      }} className="flex max-h-[85dvh] flex-col gap-0 overflow-hidden p-0 sm:max-w-[680px]">
        <DialogHeader className="shrink-0 border-b border-border/80 px-6 py-4 pr-12">
          <DialogTitle>{t('settings')}</DialogTitle>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {/* Language Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">{t('language')}</Label>
            <div className="grid grid-cols-2 gap-2">
              {languages.map((lang) => (
                <button
                  key={lang.id}
                  type="button"
                  aria-pressed={tempLanguage === lang.id}
                  onClick={() => setTempLanguage(lang.id as any)}
                  className={cn(
                    'flex items-center justify-between gap-2 rounded-md border p-3 text-left text-sm shadow-xs transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                    tempLanguage === lang.id
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-border/80 bg-card'
                  )}
                >
                  <div>
                    <div className="font-medium">{lang.nativeName}</div>
                    {lang.name !== lang.nativeName && (
                      <div className="text-xs text-muted-foreground">{lang.name}</div>
                    )}
                  </div>
                  {tempLanguage === lang.id && (
                    <Check className="h-4 w-4 text-primary" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Model Routing */}
          <section aria-label={t('modelRouting')} className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">{t('modelRouting')}</h2>
              <Badge variant="subtle" className="font-normal">
                {t(publicModels?.source === 'gateway' ? 'catalogSourceGateway' : publicModels?.source === 'siliconflow' ? 'catalogSourceSiliconFlow' : 'catalogSourceStatic')}
                <span aria-hidden="true">·</span>
                {t('modelCatalogCount').replace('{count}', String(allModels.length))}
              </Badge>
            </div>
            <div role="group" aria-label={t('modelRouting')} className="grid min-w-0 grid-cols-2 gap-1 rounded-lg border border-border/80 bg-surface-subtle/50 p-1">
              {(['primary', 'reasoning'] as const).map(role => (
                <button
                  key={role}
                  type="button"
                  aria-pressed={modelRole === role}
                  onClick={() => setModelRole(role)}
                  className={cn('min-w-0 space-y-1 rounded-md border border-transparent px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50', modelRole === role ? 'border-border/80 bg-card shadow-xs' : 'hover:bg-accent/60')}
                >
                  <span className={cn('block text-xs font-medium', modelRole === role ? 'text-primary' : 'text-muted-foreground')}>{t(role === 'primary' ? 'primaryModel' : 'reasoningModel')}</span>
                  <span className="block truncate text-sm font-medium" title={role === 'primary' ? tempModel : tempReasoningModel || t('followPrimaryDescription')}>{role === 'primary' ? primaryName : reasoningName}</span>
                </button>
              ))}
            </div>
            <p className="text-xs leading-5 text-muted-foreground">{t(modelRole === 'primary' ? 'primaryModelDescription' : 'reasoningModelDescription')}</p>
            {allModels.length > 8 && (
              <Input value={modelQuery} onChange={event => setModelQuery(event.target.value)} placeholder={t('filterModels')} aria-label="Filter models" className="h-8 text-xs" />
            )}
            <div className="max-h-56 space-y-3 overflow-y-auto pr-1">
              {modelRole === 'reasoning' && (
                <button
                  type="button"
                  aria-pressed={!tempReasoningModel}
                  onClick={() => setReasoningModelDraft('')}
                  className={cn('flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50', !tempReasoningModel && 'bg-primary/10 text-primary')}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{t('followPrimaryModel')}</span>
                    <span className="block text-xs leading-5 text-muted-foreground">{t('followPrimaryDescription')}</span>
                  </span>
                  {!tempReasoningModel && <Check aria-hidden="true" className="h-4 w-4 shrink-0" />}
                </button>
              )}
              {filteredProviders.map(provider => (
                <fieldset key={provider.id} className="min-w-0 space-y-1 rounded-lg border border-border/80 bg-card p-2">
                  <legend className="px-1.5 text-xs font-semibold text-muted-foreground">{provider.name}</legend>
                  {provider.models.map(model => (
                    <button
                      key={model.id}
                      type="button"
                      aria-pressed={activeModel === model.id}
                      onClick={() => modelRole === 'primary' ? setTempModel(model.id) : setReasoningModelDraft(model.id)}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                        activeModel === model.id && 'bg-primary/10 font-medium text-primary'
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate" title={model.id}>{model.name}</span>
                      {model.isReasoning && <Badge variant="subtle" className="shrink-0">{t('reasoningBadge')}</Badge>}
                      {model.isVision && <Badge variant="subtle" className="shrink-0">{t('visionBadge')}</Badge>}
                      {model.isPro && <Badge variant="subtle" className="shrink-0">{t('proBadge')}</Badge>}
                      {activeModel === model.id && <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />}
                    </button>
                  ))}
                </fieldset>
              ))}
              {filteredProviders.length === 0 && <p role="status" className="py-4 text-center text-xs text-muted-foreground">{t('noModelsFound')}</p>}
            </div>
          </section>

          {/* API Key Configuration */}
          <div className="space-y-3 border-t pt-4">
            <Label className="text-sm font-medium">{t('apiKeyConfiguration')}</Label>
            <p className="text-xs text-muted-foreground">{t('apiKeyOptional')}</p>

            <div className="space-y-2">
              {modelProviders.map((provider) => (
                <div key={provider.id} className="overflow-hidden rounded-lg border border-border/80 bg-card">
                  <button
                    type="button"
                    aria-expanded={expandedProvider === provider.id}
                    onClick={() => setExpandedProvider(expandedProvider === provider.id ? null : provider.id)}
                    className="flex w-full items-center justify-between gap-2 p-3 text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{provider.name}</span>
                      {apiKeys[provider.id] && (
                        <Badge variant="success">Configured</Badge>
                      )}
                    </div>
                    <ChevronDown
                      className={cn(
                        'h-4 w-4 transition-transform',
                        expandedProvider === provider.id && 'rotate-180'
                      )}
                    />
                  </button>

                  {expandedProvider === provider.id && (
                    <div className="space-y-3 border-t border-border/70 bg-surface-subtle/50 p-3">
                      <div>
                        <Label className="text-xs font-medium mb-1.5 block">{t('apiKey')}</Label>
                        <Input
                          type="password"
                          placeholder={t('apiKeyPlaceholder')}
                          value={apiKeys[provider.id] || ''}
                          onChange={(e) => handleApiKeyChange(provider.id, e.target.value)}
                          className="font-mono text-sm"
                        />
                        <p className="text-xs text-muted-foreground mt-1.5">
                          {t('apiKeyOptional')}
                        </p>
                      </div>

                      <p className="text-xs text-muted-foreground pt-1 border-t">
                        <span className="font-medium">{t('supportedModels')}:</span> {provider.models.map(m => m.name).join(', ')}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* MCP Configuration */}
          <div ref={mcpSectionRef} tabIndex={-1} className="scroll-mt-5 border-t pt-4 outline-none">
            <McpServersPanel ref={mcpPanelRef} {...mcp} disabled={saving} onSavingChange={setSaving} />
          </div>
        </div>

        <DialogFooter className="shrink-0 border-t border-border/80 bg-surface-subtle/50 px-6 py-3.5">
          <Button variant="outline" onClick={handleCancel} disabled={saving}>
            {t('cancel')}
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {t('save')}
          </Button>
        </DialogFooter>
      </DialogContent>
  )
}
