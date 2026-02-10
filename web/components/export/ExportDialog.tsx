'use client'

import React, { useState, useRef } from 'react'
import { cn } from '@/lib/utils'
import { Download, FileText, File, X, Check } from 'lucide-react'
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
type TemplateStyle = 'default' | 'academic' | 'business' | 'minimal'

const TEMPLATES: Array<{
  id: TemplateStyle
  name: string
  description: string
  preview: string
}> = [
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
  const [format, setFormat] = useState<ExportFormat>('pdf')
  const [template, setTemplate] = useState<TemplateStyle>('default')
  const [title, setTitle] = useState('Research Report')
  const [isExporting, setIsExporting] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef, isOpen, onClose)

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
        const error = await response.json()
        throw new Error(error.detail || 'Export failed')
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-dialog-title"
        className={cn(
          "w-full max-w-lg mx-4 rounded-2xl glass-strong p-6 shadow-2xl animate-scale-in",
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg gradient-accent">
              <Download className="h-5 w-5 text-white" />
            </div>
            <div>
              <h3 id="export-dialog-title" className="font-semibold text-lg">Export Report</h3>
              <p className="text-xs text-muted-foreground">Choose format and style</p>
            </div>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
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
            className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-muted focus:outline-none focus:ring-2 focus:ring-blue-500/30"
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
                  onClick={() => setFormat(f.id)}
                  aria-label={`Export as ${f.name}: ${f.description}`}
                  className={cn(
                    "flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all",
                    format === f.id
                      ? "border-blue-500/50 bg-blue-500/10"
                      : "border-muted hover:border-muted-foreground/30"
                  )}
                >
                  <Icon className={cn(
                    "h-5 w-5",
                    format === f.id ? "text-blue-500" : "text-muted-foreground"
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
            {TEMPLATES.map(t => (
              <button
                key={t.id}
                onClick={() => setTemplate(t.id)}
                aria-label={`Template: ${t.name} — ${t.description}`}
                className={cn(
                  "flex items-center gap-3 p-3 rounded-xl border transition-all text-left",
                  template === t.id
                    ? "border-purple-500/50 bg-purple-500/10"
                    : "border-muted hover:border-muted-foreground/30"
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
                  <Check className="h-4 w-4 text-purple-500 flex-shrink-0" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Export Button */}
        <Button
          variant="gradient"
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
