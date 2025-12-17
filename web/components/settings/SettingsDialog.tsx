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
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { Check } from 'lucide-react'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedModel: string
  onModelChange: (model: string) => void
}

const models = [
  { id: 'gpt-4o', name: 'GPT-4o' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
  { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet' },
  { id: 'deepseek-chat', name: 'DeepSeek Chat' },
  { id: 'gemini-pro', name: 'Gemini Pro' },
]

const languages = [
  { id: 'en', name: 'English', nativeName: 'English' },
  { id: 'zh', name: 'Chinese', nativeName: '中文' },
]

export function SettingsDialog({ open, onOpenChange, selectedModel, onModelChange }: SettingsDialogProps) {
  const { language, setLanguage, t } = useI18n()
  const [tempModel, setTempModel] = useState(selectedModel)
  const [tempLanguage, setTempLanguage] = useState(language)

  useEffect(() => {
    setTempModel(selectedModel)
  }, [selectedModel])

  useEffect(() => {
    setTempLanguage(language)
  }, [language])

  const handleSave = () => {
    onModelChange(tempModel)
    setLanguage(tempLanguage as any)
    onOpenChange(false)
  }

  const handleCancel = () => {
    setTempModel(selectedModel)
    setTempLanguage(language)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
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
            <div className="space-y-2">
              {models.map((model) => (
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
                  <span>{model.name}</span>
                  {tempModel === model.id && (
                    <Check className="h-4 w-4 text-primary" />
                  )}
                </button>
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
