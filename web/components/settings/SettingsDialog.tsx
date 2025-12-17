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
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { Check, ChevronDown } from 'lucide-react'

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

const modelProviders: ModelProvider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    models: [
      { id: 'gpt-4o', name: 'GPT-4o' },
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    models: [
      { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet' },
      { id: 'claude-3-opus', name: 'Claude 3 Opus' },
    ]
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    models: [
      { id: 'deepseek-chat', name: 'DeepSeek Chat' },
      { id: 'deepseek-coder', name: 'DeepSeek Coder' },
    ]
  },
  {
    id: 'zhipu',
    name: 'Zhipu AI (GLM)',
    models: [
      { id: 'glm-4', name: 'GLM-4' },
      { id: 'glm-4-plus', name: 'GLM-4 Plus' },
    ]
  },
  {
    id: 'qwen',
    name: 'Qwen (Alibaba)',
    models: [
      { id: 'qwen-max', name: 'Qwen Max' },
      { id: 'qwen-plus', name: 'Qwen Plus' },
      { id: 'qwen-turbo', name: 'Qwen Turbo' },
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

  const handleSave = () => {
    onModelChange(tempModel)
    setLanguage(tempLanguage as any)
    localStorage.setItem('weaver-api-keys', JSON.stringify(apiKeys))
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
                    <div className="p-3 border-t bg-muted/20">
                      <Input
                        type="password"
                        placeholder={t('apiKeyPlaceholder')}
                        value={apiKeys[provider.id] || ''}
                        onChange={(e) => handleApiKeyChange(provider.id, e.target.value)}
                        className="font-mono text-sm"
                      />
                      <p className="text-xs text-muted-foreground mt-2">
                        {provider.models.map(m => m.name).join(', ')}
                      </p>
                    </div>
                  )}
                </div>
              ))}
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
