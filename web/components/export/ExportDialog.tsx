'use client'

import React, { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { Download, FileText, File, X, Check } from '@/components/ui/icons'
import { Button } from '@/components/ui/button'
import { showSuccess, showError } from '@/lib/toast-utils'
import { getApiBaseUrl } from '@/lib/api'
import { useFocusTrap } from '@/hooks/useFocusTrap'

interface ExportDialogProps {
  threadId: string
  isOpen: boolean
  onClose: () => void
  className?: string
}

type ExportFormat = 'html' | 'pdf' | 'docx'
type TemplateStyle = string

type TemplateOption = {
  id: TemplateStyle
  name: string
  description: string
  preview: string
}

const LOCAL_TEMPLATES: TemplateOption[] = [
    {
      id: 'default',
      name: 'Default',
      description: 'Standard research report format',
      preview: '📄',
    },
    {
      id: 'academic',
      name: 'Academic',
      description: 'Formal style for research papers',
      preview: '📚',
    },
    {
      id: 'business',
      name: 'Business',
      description: 'Professional business report',
      preview: '💼',
    },
    {
      id: 'minimal',
      name: 'Minimal',
      description: 'Clean, simple formatting',
      preview: '📋',
    },
  ]

const TEMPLATE_PREVIEWS: Record<string, string> = {
  default: '📄',
  academic: '📚',
  business: '💼',
  minimal: '📋',
}

const FORMATS: Array<{
  id: ExportFormat
  name: string
  icon: React.ComponentType<{ className?: string }>
  description: string
}> = [
    { id: 'html', name: 'HTML', icon: FileText, description: 'Web page format' },
    { id: 'pdf', name: 'PDF', icon: File, description: 'Print-ready document' },
    { id: 'docx', name: 'Word', icon: File, description: 'Microsoft Word' },
  ]

export function ExportDialog({ threadId, isOpen, onClose, className }: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>('html')
  const [template, setTemplate] = useState<TemplateStyle>('default')
  const [title, setTitle] = useState('Research Report')
  const [isExporting, setIsExporting] = useState(false)
  const [templates, setTemplates] = useState<TemplateOption[]>(LOCAL_TEMPLATES)
  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef, isOpen, onClose)

  useEffect(() => {
    if (!isOpen) return

    let cancelled = false

    const loadTemplates = async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/export/templates`)
        if (!res.ok) return

        const data = await res.json()
        const remote = Array.isArray(data?.templates) ? data.templates : null
        if (!remote) return

        const normalized: TemplateOption[] = remote
          .filter((t: any) => t && typeof t === 'object' && typeof t.id === 'string')
          .map((t: any): TemplateOption => ({
            id: String(t.id),
            name: String(t.name || t.id),
            description: String(t.description || ''),
            preview: TEMPLATE_PREVIEWS[String(t.id)] || '📄',
          }))

        if (!cancelled && normalized.length) {
          setTemplates(normalized)
          // Keep selection valid if backend template list changed.
          setTemplate((prev) =>
            normalized.some((t) => t.id === prev) ? prev : normalized[0]!.id
          )
        }
      } catch {
        // Non-fatal: keep local templates when backend is unreachable.
      }
    }

    loadTemplates()

    return () => {
      cancelled = true
    }
  }, [isOpen])

  const handleExport = async () => {
    setIsExporting(true)
    try {
      const params = new URLSearchParams({
        format,
        template,
        title,
      })

      const response = await fetch(
        `${getApiBaseUrl()}/api/export/${threadId}?${params.toString()}`
      )

      if (!response.ok) {
        let message = 'Export failed'
        try {
          const error = await response.json()
          if (typeof error?.error === 'string' && error.error.trim()) message = error.error
          else if (typeof error?.detail === 'string' && error.detail.trim()) message = error.detail
          else if (typeof error?.message === 'string' && error.message.trim()) message = error.message
          else if (Array.isArray(error?.detail)) {
            const parts = error.detail
              .map((item: any) => (typeof item?.message === 'string' ? item.message : ''))
              .filter(Boolean)
            if (parts.length) message = parts.join('; ')
          }
        } catch {
          // ignore JSON parse errors
        }
        throw new Error(message)
      }

      // Get the blob and download
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report_${threadId}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)

      showSuccess('Report exported successfully', 'export')
      onClose()
    } catch (error) {
      showError(error instanceof Error ? error.message : 'Export failed', 'export')
    } finally {
      setIsExporting(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-dialog-title"
        className={cn(
          "w-full max-w-lg mx-4 rounded-2xl border border-border/60 bg-card p-6 shadow-lg",
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <Download className="h-5 w-5" />
            </div>
            <div>
              <h3 id="export-dialog-title" className="font-semibold text-lg">Export Report</h3>
              <p className="text-xs text-muted-foreground">Choose format and style</p>
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Close export dialog"
            title="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Title Input */}
        <div className="mb-6">
          <label className="text-xs font-medium text-muted-foreground block mb-2">
            Report Title
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl bg-background border border-border/60 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            placeholder="Enter report title..."
          />
        </div>

        {/* Format Selection */}
        <div className="mb-6">
          <label className="text-xs font-medium text-muted-foreground block mb-2">
            Format
          </label>
          <div className="grid grid-cols-3 gap-2">
            {FORMATS.map(f => {
              const Icon = f.icon
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFormat(f.id)}
                  aria-label={`Export as ${f.name}: ${f.description}`}
                  className={cn(
                    "flex flex-col items-center gap-1.5 p-3 rounded-xl border border-border/60 transition-colors duration-200",
                    format === f.id
                      ? "border-primary/30 bg-primary/10 text-primary"
                      : "hover:bg-accent"
                  )}
                >
                  <Icon className={cn(
                    "h-5 w-5",
                    format === f.id ? "text-primary" : "text-muted-foreground"
                  )} />
                  <span className="text-xs font-medium">{f.name}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Template Selection */}
        <div className="mb-6">
          <label className="text-xs font-medium text-muted-foreground block mb-2">
            Template Style
          </label>
          <div className="grid grid-cols-2 gap-2">
            {templates.map(t => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTemplate(t.id)}
                aria-label={`Template: ${t.name} — ${t.description}`}
                className={cn(
                  "flex items-center gap-3 p-3 rounded-xl border border-border/60 transition-colors duration-200 text-left",
                  template === t.id
                    ? "border-primary/30 bg-primary/10"
                    : "hover:bg-accent"
                )}
              >
                <span className="text-2xl">{t.preview}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{t.name}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {t.description}
                  </div>
                </div>
                {template === t.id && (
                  <Check className="h-4 w-4 text-primary flex-shrink-0" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Export Button */}
        <Button
          variant="default"
          className="w-full"
          onClick={handleExport}
          loading={isExporting}
        >
          <Download className="h-4 w-4 mr-2" />
          Export as {format.toUpperCase()}
        </Button>
      </div>
    </div>
  )
}
