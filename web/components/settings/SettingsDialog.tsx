'use client'

import React, { useState, useEffect, useMemo } from 'react'
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
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { Check, ChevronDown, Plug, RefreshCw, CheckCircle2 } from 'lucide-react'
import { toast } from 'sonner'
import { getApiBaseUrl } from '@/lib/api'
import { usePublicModels } from '@/hooks/usePublicModels'
import { useStoredPreference } from '@/hooks/useStoredPreference'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedModel: string
  onModelChange: (model: string) => void
}

interface ModelProvider {
  id: string
  name: string
  models: { id: string; name: string }[]
}

const getModelProviders = (t: (key: any) => string): ModelProvider[] => [
  {
    id: 'openai',
    name: 'OpenAI',
    models: [
      { id: 'gpt-5', name: 'GPT-5' },
      { id: 'gpt-4.1', name: 'GPT-4.1' },
      { id: 'gpt-4o', name: 'GPT-4o' },
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    models: [
      { id: 'claude-sonnet-4-5-20250514', name: 'Claude Sonnet 4.5' },
      { id: 'claude-opus-4-20250514', name: 'Claude Opus 4' },
      { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4' },
    ]
  },
  {
    id: 'deepseek',
    name: t('deepseek'),
    models: [
      { id: 'deepseek-chat', name: 'deepseek-chat' },
      { id: 'deepseek-reasoner', name: 'deepseek-reasoner' },
    ]
  },
  {
    id: 'qwen',
    name: t('qwen'),
    models: [
      { id: 'qwen-plus', name: 'qwen-plus' },
      { id: 'qwen3-vl-flash', name: 'qwen3-vl-flash' },
    ]
  },
  {
    id: 'zhipu',
    name: t('zhipu'),
    models: [
      { id: 'glm-4.6', name: 'GLM-4.6' },
      { id: 'glm-4.6v', name: 'glm-4.6v' },
    ]
  }
]

const languages = [
  { id: 'en', name: 'English', nativeName: 'English' },
  { id: 'zh', name: 'Chinese', nativeName: '中文' },
  { id: 'ja', name: 'Japanese', nativeName: '日本語' },
  { id: 'ko', name: 'Korean', nativeName: '한국어' },
]

interface ApiKeys {
  [key: string]: string
}

export function SettingsDialog({ open, onOpenChange, selectedModel, onModelChange }: SettingsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <SettingsDialogContent onOpenChange={onOpenChange} selectedModel={selectedModel} onModelChange={onModelChange} />}
    </Dialog>
  )
}

function SettingsDialogContent({ onOpenChange, selectedModel, onModelChange }: Omit<SettingsDialogProps, 'open'>) {
  const { language, setLanguage, t } = useI18n()
  const { models: publicModels } = usePublicModels()
  const [modelDraft, setTempModel] = useState<string | null>(null)
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

  // MCP state
  const [mcpEnabled, setMcpEnabled] = useState(false)
  const [mcpConfig, setMcpConfig] = useState('{}')
  const [mcpLoadedTools, setMcpLoadedTools] = useState(0)
  const [mcpLoading, setMcpLoading] = useState(true)
  const [mcpLoaded, setMcpLoaded] = useState(false)

  const staticModelProviders = getModelProviders(t)
  const allowlist = publicModels?.options?.length ? new Set(publicModels.options) : null
  const requestedModel = modelDraft ?? selectedModel
  const tempModel = allowlist && !allowlist.has(requestedModel)
    ? (publicModels?.default && allowlist.has(publicModels.default) ? publicModels.default : publicModels!.options[0])
    : requestedModel

  const modelProviders: ModelProvider[] = allowlist
    ? (() => {
        const known = staticModelProviders.flatMap((p) => p.models.map((m) => m.id))
        const filtered = staticModelProviders
          .map((provider) => ({
            ...provider,
            models: provider.models.filter((m) => allowlist.has(m.id)),
          }))
          .filter((provider) => provider.models.length > 0)

        const unknown = publicModels!.options.filter((id) => !known.includes(id))
        if (unknown.length > 0) {
          filtered.push({
            id: 'custom',
            name: 'Custom',
            models: unknown.map((id) => ({ id, name: id })),
          })
        }
        return filtered
      })()
    : staticModelProviders

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/mcp/config`, { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch config')
        const data = await res.json()
        if (controller.signal.aborted) return
        setMcpEnabled(data.enabled)
        setMcpConfig(JSON.stringify(data.servers, null, 2))
        setMcpLoadedTools(data.loaded_tools || 0)
        setMcpLoaded(true)
      } catch (e) {
        if (controller.signal.aborted) return
        console.error(e)
        toast.error('Failed to load MCP config')
      } finally {
        if (!controller.signal.aborted) setMcpLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [])

  // Save MCP config
  const saveMcpConfig = async () => {
    try {
      setMcpLoading(true)
      let parsedServers = {}
      try {
        parsedServers = JSON.parse(mcpConfig.trim() || '{}')
        if (!parsedServers || typeof parsedServers !== 'object' || Array.isArray(parsedServers)) {
          throw new Error('MCP servers must be an object')
        }
      } catch (e) {
        toast.error('Invalid JSON configuration')
        setMcpLoading(false)
        return false
      }

      const res = await fetch(`${getApiBaseUrl()}/api/mcp/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enable: mcpEnabled,
          servers: parsedServers
        })
      })

      if (!res.ok) throw new Error('Failed to save config')

      const data = await res.json()
      setMcpLoadedTools(data.loaded_tools || 0)
      toast.success(data.message || 'MCP configuration saved')
      return true
    } catch (e) {
      console.error(e)
      toast.error('Failed to save MCP config')
      return false
    } finally {
      setMcpLoading(false)
    }
  }

  const handleApiKeyChange = (provider: string, value: string) => {
    setApiKeys({
      ...apiKeys,
      [provider]: value
    })
  }

  const handleSave = async () => {
    if (!await saveMcpConfig()) return
    onModelChange(tempModel)
    setLanguage(tempLanguage)
    setSavedKeys(JSON.stringify(apiKeys))
    onOpenChange(false)
  }

  const handleCancel = () => {
    onOpenChange(false)
  }

  return (
      <DialogContent aria-describedby={undefined} className="flex max-h-[85dvh] flex-col gap-0 overflow-hidden p-0 sm:max-w-[600px]">
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

          {/* Model Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">{t('defaultModel')}</Label>
            <div className="space-y-4">
              {modelProviders.map(provider => (
                <fieldset key={provider.id} className="min-w-0 space-y-1 rounded-lg border border-border/80 bg-card p-2">
                  <legend className="px-1.5 text-xs font-semibold text-muted-foreground">{provider.name}</legend>
                  {provider.models.map(model => (
                    <button
                      key={model.id}
                      type="button"
                      aria-pressed={tempModel === model.id}
                      onClick={() => setTempModel(model.id)}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                        tempModel === model.id && 'bg-primary/10 font-medium text-primary'
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate" title={model.name}>{model.name}</span>
                      {['qwen3-vl-flash', 'glm-4.6v'].includes(model.id) && <Badge variant="subtle">Vision</Badge>}
                      {tempModel === model.id && <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />}
                    </button>
                  ))}
                </fieldset>
              ))}
            </div>
          </div>

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
          <div className="space-y-3 border-t pt-4">
            <Label className="text-sm font-medium flex items-center gap-2">
              <Plug className="h-4 w-4" />
              {t('mcpConfiguration')}
            </Label>
            <p className="text-xs text-muted-foreground">
              {t('mcpDescription')}
            </p>

            <div className="flex items-center justify-between gap-3 rounded-lg border border-border/80 bg-surface-subtle/70 p-3">
              <div className="space-y-0.5">
                <Label htmlFor="settings-mcp-enabled" className="text-sm font-medium">{t('enableMcp')}</Label>
                <div className="text-xs text-muted-foreground">
                  {mcpEnabled ? t('mcpActive') : t('mcpDisabled')}
                </div>
              </div>
              <Switch
                id="settings-mcp-enabled"
                checked={mcpEnabled}
                onCheckedChange={setMcpEnabled}
                disabled={mcpLoading || !mcpLoaded}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="settings-mcp-config" className="text-xs font-medium">{t('serversConfiguration')}</Label>
              <Textarea
                id="settings-mcp-config"
                value={mcpConfig}
                onChange={(e) => setMcpConfig(e.target.value)}
                disabled={mcpLoading || !mcpLoaded}
                className="font-mono text-xs min-h-[120px]"
                placeholder='{ "server-name": { "command": "...", "args": [...] } }'
              />
              <p className="text-xs text-muted-foreground">
                {t('serversConfigHint')}
              </p>
            </div>

            <div role="status" className="flex items-center gap-2 rounded-md border border-border/60 bg-surface-subtle/60 px-3 py-2 text-xs text-muted-foreground">
              {mcpLoading ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <CheckCircle2 className={cn('h-3.5 w-3.5', mcpEnabled && 'text-success')} />
              )}
              <span>{t('loadedTools')}: <span className="font-medium tabular-nums text-foreground">{mcpLoadedTools}</span></span>
            </div>
          </div>
        </div>

        <DialogFooter className="shrink-0 border-t border-border/80 bg-surface-subtle/50 px-6 py-3.5">
          <Button variant="outline" onClick={handleCancel}>
            {t('cancel')}
          </Button>
          <Button onClick={handleSave} disabled={mcpLoading || !mcpLoaded}>
            {t('save')}
          </Button>
        </DialogFooter>
      </DialogContent>
  )
}
