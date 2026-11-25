'use client'

import React, { useRef, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Plug, RefreshCw } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { useMcpConfig } from '@/hooks/useMcpConfig'
import { McpServersPanel, type McpServersPanelHandle } from './McpServersPanel'

export function McpConfigDialog() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t('mcpConfiguration')} title={t('mcpConfiguration')}><Plug className="h-4 w-4 text-muted-foreground" aria-hidden="true" /></Button>
      </DialogTrigger>
      {open && <McpConfigContent onClose={() => setOpen(false)} />}
    </Dialog>
  )
}

function McpConfigContent({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const mcp = useMcpConfig()
  const panelRef = useRef<McpServersPanelHandle>(null)
  const [saving, setSaving] = useState(false)
  const handleSave = async () => {
    if (await panelRef.current?.save()) onClose()
  }
  return (
    <DialogContent aria-describedby={undefined} className="flex max-h-[85dvh] flex-col gap-0 overflow-hidden p-0 sm:max-w-[680px]">
      <DialogHeader className="shrink-0 border-b border-border/80 px-6 py-4 pr-12"><DialogTitle>{t('mcpConfiguration')}</DialogTitle></DialogHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5"><McpServersPanel ref={panelRef} {...mcp} disabled={saving} onSavingChange={setSaving} /></div>
      <DialogFooter className="shrink-0 border-t border-border/80 bg-surface-subtle/50 px-6 py-3.5">
        <Button variant="outline" onClick={onClose} disabled={saving}>{t('cancel')}</Button>
        <Button onClick={handleSave} disabled={saving || mcp.isLoading || !mcp.config}>{saving && <RefreshCw className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}{t('mcpSaveReload')}</Button>
      </DialogFooter>
    </DialogContent>
  )
}
