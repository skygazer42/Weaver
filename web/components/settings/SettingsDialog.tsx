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
  defaultBaseUrl?: string
}

const modelProviders: ModelProvider[] = [
  {
    id: 'deepseek',
    name: 'DeepSeek',
    defaultBaseUrl: 'https://api.deepseek.com',
    models: [
      { id: 'deepseek-chat', name: 'deepseek-chat' },
      { id: 'deepseek-reasoner', name: 'deepseek-reasoner' },
    ]
  },
  {
    id: 'qwen',
    name: '通义千问 (Qwen)',
    defaultBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: [
      { id: 'qwen-max', name: 'Qwen-Max' },
      { id: 'qwen-plus', name: 'Qwen-Plus' },
      { id: 'qwen-turbo', name: 'Qwen-Turbo' },
      { id: 'qwen2.5-72b', name: 'Qwen2.5-72B' },
      { id: 'qwen-vl-max', name: 'Qwen-VL-Max 🖼️' },
      { id: 'qwen-vl-plus', name: 'Qwen-VL-Plus 🖼️' },
      { id: 'qwen-audio', name: 'Qwen-Audio 🎵' },
    ]
  },
  {
    id: 'zhipu',
    name: '智谱AI (GLM)',
    defaultBaseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    models: [
      { id: 'glm-4-plus', name: 'GLM-4-Plus' },
      { id: 'glm-4-0520', name: 'GLM-4-0520' },
      { id: 'glm-4-air', name: 'GLM-4-Air' },
      { id: 'glm-4-airx', name: 'GLM-4-AirX' },
      { id: 'glm-4-flash', name: 'GLM-4-Flash' },
      { id: 'glm-4v', name: 'GLM-4V 🖼️' },
      { id: 'glm-4v-plus', name: 'GLM-4V-Plus 🖼️' },
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

interface BaseUrls {
  [key: string]: string
}

export function SettingsDialog({ open, onOpenChange, selectedModel, onModelChange }: SettingsDialogProps) {
  const { language, setLanguage, t } = useI18n()
  const [tempModel, setTempModel] = useState(selectedModel)
  const [tempLanguage, setTempLanguage] = useState(language)
  const [apiKeys, setApiKeys] = useState<ApiKeys>({})
  const [baseUrls, setBaseUrls] = useState<BaseUrls>({})
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null)

  // Load API keys and base URLs from localStorage
  useEffect(() => {
    const savedKeys = localStorage.getItem('weaver-api-keys')
    if (savedKeys) {
      try {
        setApiKeys(JSON.parse(savedKeys))
      } catch (e) {
        console.error('Failed to parse API keys', e)
      }
    }

    const savedBaseUrls = localStorage.getItem('weaver-base-urls')
    if (savedBaseUrls) {
      try {
        setBaseUrls(JSON.parse(savedBaseUrls))
      } catch (e) {
        console.error('Failed to parse base URLs', e)
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

  const handleBaseUrlChange = (provider: string, value: string) => {
    setBaseUrls(prev => ({
      ...prev,
      [provider]: value
    }))
  }

  const handleSave = () => {
    onModelChange(tempModel)
    setLanguage(tempLanguage as any)
    localStorage.setItem('weaver-api-keys', JSON.stringify(apiKeys))
    localStorage.setItem('weaver-base-urls', JSON.stringify(baseUrls))
    onOpenChange(false)
  }

  const handleCancel = () => {
    setTempModel(selectedModel)
    setTempLanguage(language)
    // Reload saved API keys and base URLs
    const savedKeys = localStorage.getItem('weaver-api-keys')
    if (savedKeys) {
      try {
        setApiKeys(JSON.parse(savedKeys))
      } catch (e) {
        console.error('Failed to parse API keys', e)
      }
    }
    const savedBaseUrls = localStorage.getItem('weaver-base-urls')
    if (savedBaseUrls) {
      try {
        setBaseUrls(JSON.parse(savedBaseUrls))
      } catch (e) {
        console.error('Failed to parse base URLs', e)
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
                        <Label className="text-xs font-medium mb-1.5 block">{t('baseUrl')}</Label>
                        <Input
                          type="text"
                          placeholder={provider.defaultBaseUrl || t('baseUrlPlaceholder')}
                          value={baseUrls[provider.id] || ''}
                          onChange={(e) => handleBaseUrlChange(provider.id, e.target.value)}
                          className="font-mono text-xs"
                        />
                        {provider.defaultBaseUrl && (
                          <p className="text-xs text-muted-foreground mt-1">
                            默认: {provider.defaultBaseUrl}
                          </p>
                        )}
                      </div>

                      <div>
                        <Label className="text-xs font-medium mb-1.5 block">{t('apiKey')}</Label>
                        <Input
                          type="password"
                          placeholder={t('apiKeyPlaceholder')}
                          value={apiKeys[provider.id] || ''}
                          onChange={(e) => handleApiKeyChange(provider.id, e.target.value)}
                          className="font-mono text-sm"
                        />
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
