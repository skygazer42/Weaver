'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { useI18n } from '@/lib/i18n/i18n-context'
import { TranslationKey, Language } from '@/lib/i18n/translations'
import { cn } from '@/lib/utils'
import { Check, ChevronDown, Plug, RefreshCw, CheckCircle2, Search } from 'lucide-react'
import { toast } from 'sonner'
import { getMcpConfig, updateMcpConfig, getSearchProviders, type SearchProviderSnapshot } from '@/lib/api-client'
import { getApiBaseUrl } from '@/lib/api'
import { StorageService } from '@/lib/storage-service'

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

const getModelProviders = (t: (key: TranslationKey) => string): ModelProvider[] => [
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
      { id: 'qwen3-vl-flash', name: 'qwen3-vl-flash 🖼️' },
    ]
  },
  {
    id: 'zhipu',
    name: t('zhipu'),
    models: [
      { id: 'glm-4.6', name: 'GLM-4.6' },
      { id: 'glm-4.6v', name: 'glm-4.6v 🖼️' },
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

type McpServersPreset = Record<string, unknown>

const MCP_PRESET_FILESYSTEM_MEMORY: McpServersPreset = {
  filesystem: {
    type: 'stdio',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-filesystem', '/ABS/PATH/TO/ALLOW'],
  },
  memory: {
    type: 'stdio',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-memory'],
  },
}

export function SettingsDialog({ open, onOpenChange, selectedModel, onModelChange }: SettingsDialogProps) {
  const { language, setLanguage, t } = useI18n()
  const [tempModel, setTempModel] = useState(selectedModel)
  const [tempLanguage, setTempLanguage] = useState(language)
  const [apiKeys, setApiKeys] = useState<ApiKeys>({})
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null)

  // MCP state
  const [mcpEnabled, setMcpEnabled] = useState(false)
  const [mcpConfig, setMcpConfig] = useState('')
  const [mcpLoadedTools, setMcpLoadedTools] = useState(0)
  const [mcpLoading, setMcpLoading] = useState(false)
  const [mcpError, setMcpError] = useState<string | null>(null)

  // Search providers state
  const [searchProviders, setSearchProviders] = useState<SearchProviderSnapshot[]>([])
  const [searchProvidersLoading, setSearchProvidersLoading] = useState(false)
  const [searchProvidersError, setSearchProvidersError] = useState<string | null>(null)

  const modelProviders = getModelProviders(t)

  // Fetch MCP config
  const fetchMcpConfig = useCallback(async () => {
    try {
      setMcpLoading(true)
      setMcpError(null)
      const data = await getMcpConfig()
      setMcpEnabled(Boolean(data.enabled))
      setMcpConfig(JSON.stringify(data.servers || {}, null, 2))
      setMcpLoadedTools(data.loaded_tools || 0)
    } catch (e) {
      console.error(e)
      setMcpError(t('mcpLoadFailed'))
      toast.error(t('mcpLoadFailed'))
    } finally {
      setMcpLoading(false)
    }
  }, [t])

  const fetchSearchProviderStatus = useCallback(async () => {
    try {
      setSearchProvidersLoading(true)
      setSearchProvidersError(null)
      const data = await getSearchProviders()
      setSearchProviders(Array.isArray(data.providers) ? data.providers : [])
    } catch (e) {
      console.error(e)
      setSearchProvidersError(t('error'))
    } finally {
      setSearchProvidersLoading(false)
    }
  }, [t])

  const applyMcpPreset = useCallback((preset: McpServersPreset) => {
    setMcpEnabled(true)
    setMcpConfig((prev) => {
      const raw = String(prev || '').trim()
      if (!raw || raw === '{}' || raw === 'null') {
        return JSON.stringify(preset, null, 2)
      }

      try {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          // Merge without overwriting existing server ids.
          return JSON.stringify({ ...preset, ...(parsed as Record<string, unknown>) }, null, 2)
        }
      } catch {
        // Ignore invalid JSON; replace with preset.
      }

      return JSON.stringify(preset, null, 2)
    })
    toast.success(t('mcpPresetApplied'))
  }, [t])

  // Save MCP config
  const saveMcpConfig = async () => {
    try {
      setMcpLoading(true)
      setMcpError(null)
      let parsedServers = {}
      try {
        parsedServers = JSON.parse(mcpConfig)
      } catch (e) {
        toast.error('Invalid JSON configuration')
        setMcpLoading(false)
        return false
      }

      const data = await updateMcpConfig({
        enable: mcpEnabled,
        servers: parsedServers,
      })

      setMcpLoadedTools(data.loaded_tools || 0)
      toast.success('MCP configuration saved')
      return true
    } catch (e) {
      console.error(e)
      setMcpError(t('mcpSaveFailed'))
      toast.error(t('mcpSaveFailed'))
      return false
    } finally {
      setMcpLoading(false)
    }
  }

  // Load API keys from StorageService
  useEffect(() => {
    setApiKeys(StorageService.getApiKeys())
  }, [])

  // Fetch MCP config when dialog opens
  useEffect(() => {
    if (open) {
      void fetchMcpConfig()
      void fetchSearchProviderStatus()
    }
  }, [open, fetchMcpConfig, fetchSearchProviderStatus])

  useEffect(() => {
    setTempModel(selectedModel)
  }, [selectedModel])

  useEffect(() => {
    setTempLanguage(language)
  }, [language])

  const handleApiKeyChange = (provider: string, value: string) => {
    setApiKeys(prev => ({
      ...prev,
      [provider]: value
    }))
  }

  const handleSave = async () => {
    onModelChange(tempModel)
    setLanguage(tempLanguage as Language)
    StorageService.saveApiKeys(apiKeys)
    await saveMcpConfig()
    onOpenChange(false)
  }

  const handleCancel = () => {
    setTempModel(selectedModel)
    setTempLanguage(language)
    // Reload saved API keys
    setApiKeys(StorageService.getApiKeys())
    onOpenChange(false)
  }

  const allModels = modelProviders.flatMap(provider =>
    provider.models.map(model => ({ ...model, provider: provider.id }))
  )

  const formatSeconds = (value: number | null | undefined) => {
    if (value == null || Number.isNaN(value)) return null
    const seconds = Math.max(0, value)
    if (seconds < 60) return `${Math.round(seconds)}s`
    const mins = seconds / 60
    if (mins < 10) return `${mins.toFixed(1)}m`
    return `${Math.round(mins)}m`
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('settings')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Language Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">{t('language')}</Label>
            <div className="grid grid-cols-2 gap-2">
	              {languages.map((lang) => (
	                <button
	                  key={lang.id}
	                  onClick={() => setTempLanguage(lang.id as Language)}
	                  className={cn(
	                    'flex items-center justify-between rounded-lg border-2 p-3 text-left transition-colors duration-200 hover:bg-muted/50',
	                    tempLanguage === lang.id
	                      ? 'border-primary bg-primary/5'
	                      : 'border-border'
	                  )}
	                >
                  <div>
                    <div className="font-medium">{lang.nativeName}</div>
                    <div className="text-xs text-muted-foreground">{lang.name}</div>
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
            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
	              {allModels.map((model) => (
	                <button
	                  key={model.id}
	                  onClick={() => setTempModel(model.id)}
	                  className={cn(
	                    'flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors duration-200 hover:bg-muted/50',
	                    tempModel === model.id
	                      ? 'border-primary bg-primary/5 font-medium'
	                      : 'border-border'
	                  )}
	                >
                  <div>
                    <div className="font-medium">{model.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {modelProviders.find(p => p.id === model.provider)?.name}
                    </div>
                  </div>
                  {tempModel === model.id && (
                    <Check className="h-4 w-4 text-primary" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* API Key Configuration */}
          <div className="space-y-3 border-t pt-4">
            <Label className="text-sm font-medium">{t('apiKeyConfiguration')}</Label>
            <p className="text-xs text-muted-foreground">{t('apiKeyOptional')}</p>

            <div className="space-y-2">
              {modelProviders.map((provider) => (
                <div key={provider.id} className="border rounded-lg overflow-hidden">
                  <button
                    onClick={() => setExpandedProvider(expandedProvider === provider.id ? null : provider.id)}
                    className="flex w-full items-center justify-between p-3 hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{provider.name}</span>
                      {apiKeys[provider.id] && (
                        <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded">
                          {t('apiKey')} ✓
                        </span>
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
                    <div className="p-3 border-t bg-muted/20 space-y-3">
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

            <div className="flex items-center justify-between space-x-2 border p-3 rounded-lg bg-muted/20">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{t('enableMcp')}</Label>
                <div className="text-xs text-muted-foreground">
                  {mcpEnabled ? t('mcpActive') : t('mcpDisabled')}
                </div>
              </div>
              <Switch
                checked={mcpEnabled}
                onCheckedChange={setMcpEnabled}
              />
            </div>

            {mcpError ? (
              <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                <div className="font-medium">{mcpError}</div>
                <div className="mt-1 text-destructive/80">{t('mcpLoadHint')}</div>
                <div className="mt-1 font-mono text-[11px] text-destructive/70">{getApiBaseUrl()}</div>
              </div>
            ) : null}

            <div className="space-y-2">
              <Label className="text-xs font-medium">{t('serversConfiguration')}</Label>
              {mcpLoading ? (
                <div className="space-y-2 animate-pulse">
                  <div className="h-[120px] w-full bg-muted/30 rounded-lg" />
                  <div className="h-4 w-2/3 bg-muted/20 rounded" />
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <Label className="text-xs font-medium">{t('mcpPresets')}</Label>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => applyMcpPreset(MCP_PRESET_FILESYSTEM_MEMORY)}
                      >
                        {t('mcpPresetFsMemory')}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t('mcpPresetsHint')}
                    </p>
                  </div>
                  <Textarea
                    value={mcpConfig}
                    onChange={(e) => setMcpConfig(e.target.value)}
                    className="font-mono text-xs min-h-[120px]"
                    placeholder='{ "server-name": { "command": "...", "args": [...] } }'
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('serversConfigHint')}
                  </p>
                </>
              )}
            </div>

            <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground bg-muted/30 p-2 rounded">
              <div className="flex items-center gap-2">
                {mcpLoading ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3 w-3 text-green-500" />
                )}
                <span>{t('loadedTools')}: {mcpLoadedTools}</span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={mcpLoading}
                onClick={fetchMcpConfig}
                aria-label={t('refresh')}
                title={t('refresh')}
                className="text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Search Providers */}
          <div className="space-y-3 border-t pt-4">
            <Label className="text-sm font-medium flex items-center gap-2">
              <Search className="h-4 w-4" />
              {t('searchProviders')}
            </Label>
            <p className="text-xs text-muted-foreground">{t('searchProvidersDesc')}</p>

            {searchProvidersError ? (
              <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                {searchProvidersError}
              </div>
            ) : null}

            {searchProvidersLoading ? (
              <div className="space-y-2 animate-pulse">
                <div className="h-10 w-full bg-muted/30 rounded-lg" />
                <div className="h-10 w-full bg-muted/20 rounded-lg" />
              </div>
            ) : (
              <div className="space-y-2">
                {searchProviders.length === 0 ? (
                  <div className="rounded-lg border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                    {t('noResults')}
                  </div>
                ) : (
                  searchProviders.map((p) => {
                    const circuitOpen = Boolean(p.circuit?.is_open)
                    const resetsIn = formatSeconds(p.circuit?.resets_in_seconds)
                    const availabilityLabel = p.available ? t('available') : t('unavailable')
                    const healthLabel = p.healthy ? t('healthy') : t('unhealthy')
                    const circuitLabel = circuitOpen ? t('circuitOpen') : t('circuitClosed')

                    return (
                      <div key={p.name} className="rounded-lg border bg-muted/10 px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <div className="font-medium text-sm">{p.name}</div>
                          <div className="flex items-center gap-1.5 text-[11px]">
                            <span
                              className={cn(
                                'rounded-full px-2 py-0.5 border tabular-nums',
                                p.available ? 'border-green-500/20 bg-green-500/10 text-green-700' : 'border-border bg-muted text-muted-foreground'
                              )}
                            >
                              {availabilityLabel}
                            </span>
                            <span
                              className={cn(
                                'rounded-full px-2 py-0.5 border tabular-nums',
                                p.healthy ? 'border-border bg-muted text-muted-foreground' : 'border-amber-500/20 bg-amber-500/10 text-amber-800'
                              )}
                            >
                              {healthLabel}
                            </span>
                            <span
                              className={cn(
                                'rounded-full px-2 py-0.5 border tabular-nums',
                                circuitOpen ? 'border-amber-500/20 bg-amber-500/10 text-amber-800' : 'border-border bg-muted text-muted-foreground'
                              )}
                              title={resetsIn ? `${circuitLabel} · ${resetsIn}` : circuitLabel}
                            >
                              {circuitLabel}{resetsIn ? ` · ${resetsIn}` : ''}
                            </span>
                          </div>
                        </div>

                        <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground tabular-nums">
                          <span>
                            SR {(p.success_rate * 100).toFixed(0)}% · {Math.round(p.avg_latency_ms)}ms · Q {p.avg_result_quality.toFixed(2)}
                          </span>
                          <span>
                            {p.success_count}/{p.total_calls} ok · {p.error_count} err
                          </span>
                        </div>

                        {p.last_error ? (
                          <div className="mt-1 text-[11px] text-muted-foreground truncate" title={p.last_error}>
                            {p.last_error}
                          </div>
                        ) : null}
                      </div>
                    )
                  })
                )}
              </div>
            )}

            <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground bg-muted/30 p-2 rounded">
              <span className="tabular-nums">
                {t('results')}: {searchProviders.length}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={searchProvidersLoading}
                onClick={fetchSearchProviderStatus}
                aria-label={t('refresh')}
                title={t('refresh')}
                className="text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className={cn('h-4 w-4', searchProvidersLoading && 'animate-spin')} />
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>
            {t('cancel')}
          </Button>
          <Button onClick={handleSave}>
            {t('save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
