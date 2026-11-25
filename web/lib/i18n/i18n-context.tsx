'use client'

import React, { createContext, useContext, useEffect } from 'react'
import { translations, Language, TranslationKey } from './translations'
import { useStoredPreference } from '@/hooks/useStoredPreference'

const HTML_LANG: Record<Language, string> = {
  en: 'en',
  zh: 'zh-CN',
  ja: 'ja',
  ko: 'ko',
}

interface I18nContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: TranslationKey) => string
}

const I18nContext = createContext<I18nContextType | undefined>(undefined)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [savedLanguage, setLanguage] = useStoredPreference('weaver-language', 'en')
  const language: Language = ['en', 'zh', 'ja', 'ko'].includes(savedLanguage) ? savedLanguage as Language : 'en'

  useEffect(() => {
    document.documentElement.lang = HTML_LANG[language]
  }, [language])

  // Translation function
  const t = (key: TranslationKey): string => {
    // Other languages may be partial. Fall back to English.
    const table = translations[language] as Partial<Record<TranslationKey, string>>
    return table[key] || translations.en[key] || key
  }

  return (
    <I18nContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  const context = useContext(I18nContext)
  if (context === undefined) {
    throw new Error('useI18n must be used within an I18nProvider')
  }
  return context
}
