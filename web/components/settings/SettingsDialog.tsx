'use client'

import React, { useState, useEffect } from 'react'
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
import { cn } from '@/lib/utils'
import { Check, ChevronDown, Plug, RefreshCw, CheckCircle2 } from 'lucide-react'
import { toast } from 'sonner'

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
]

interface ApiKeys {
  [key: string]: string
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

  const modelProviders = getModelProviders(t)

  // Fetch MCP config
  const fetchMcpConfig = async () => {
    try {
      setMcpLoading(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/mcp/config`)
      if (!res.ok) throw new Error('Failed to fetch config')
      const data = await res.json()
      setMcpEnabled(data.enabled)
      setMcpConfig(JSON.stringify(data.servers, null, 2))
      setMcpLoadedTools(data.loaded_tools || 0)
    } catch (e) {
      console.error(e)
    } finally {
      setMcpLoading(false)
    }
  }

  // Save MCP config
  const saveMcpConfig = async () => {
    try {
      setMcpLoading(true)
      let parsedServers = {}
      try {
        parsedServers = JSON.parse(mcpConfig)
      } catch (e) {
        toast.error('Invalid JSON configuration')
        setMcpLoading(false)
        return false
      }

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/mcp/config`, {
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

  // Load API keys from localStorage
  useEffect(() => {
    const savedKeys = localStorage.getItem('weaver-api-keys')
    if (savedKeys) {
      try {
        setApiKeys(JSON.parse(savedKeys))
      } catch (e) {
        console.error('Failed to parse API keys', e)
      }
    }
  }, [])

  // Fetch MCP config when dialog opens
  useEffect(() => {
    if (open) {
      fetchMcpConfig()
    }
  }, [open])

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
    setLanguage(tempLanguage as any)
    localStorage.setItem('weaver-api-keys', JSON.stringify(apiKeys))
    await saveMcpConfig()
    onOpenChange(false)
  }

  const handleCancel = () => {
    setTempModel(selectedModel)
    setTempLanguage(language)
    // Reload saved API keys
    const savedKeys = localStorage.getItem('weaver-api-keys')
    if (savedKeys) {
      try {
        setApiKeys(JSON.parse(savedKeys))
      } catch (e) {
        console.error('Failed to parse API keys', e)
      }
    }
    onOpenChange(false)
  }

  const allModels = modelProviders.flatMap(provider =>
    provider.models.map(model => ({ ...model, provider: provider.id }))
  )

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
                  onClick={() => setTempLanguage(lang.id as any)}
                  className={cn(
                    'flex items-center justify-between rounded-lg border-2 p-3 text-left transition-all hover:bg-muted/50',
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
                    'flex w-full items-center justify-between rounded-lg border p-3 text-left transition-all hover:bg-muted/50',
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
                        <span className="font-medium">支持模型:</span> {provider.models.map(m => m.name).join(', ')}
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
              MCP Configuration
            </Label>
            <p className="text-xs text-muted-foreground">
              Configure Model Context Protocol servers to extend capabilities.
            </p>

            <div className="flex items-center justify-between space-x-2 border p-3 rounded-lg bg-muted/20">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">Enable MCP</Label>
                <div className="text-xs text-muted-foreground">
                  {mcpEnabled ? 'MCP is currently active.' : 'MCP is disabled.'}
                </div>
              </div>
              <Switch
                checked={mcpEnabled}
                onCheckedChange={setMcpEnabled}
              />
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-medium">Servers Configuration (JSON)</Label>
              <Textarea
                value={mcpConfig}
                onChange={(e) => setMcpConfig(e.target.value)}
                className="font-mono text-xs min-h-[120px]"
                placeholder='{ "server-name": { "command": "...", "args": [...] } }'
              />
              <p className="text-xs text-muted-foreground">
                Define servers with transport, command, and args.
              </p>
            </div>

            <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 p-2 rounded">
              {mcpLoading ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3 w-3 text-green-500" />
              )}
              <span>Loaded Tools: {mcpLoadedTools}</span>
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
