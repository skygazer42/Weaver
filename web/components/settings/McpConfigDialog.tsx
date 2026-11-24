'use client'

import React, { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { Plug, RefreshCw, CheckCircle2 } from 'lucide-react'
import { getApiBaseUrl } from '@/lib/api'
import { cn } from '@/lib/utils'

export function McpConfigDialog() {
  const [open, setOpen] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [config, setConfig] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadedTools, setLoadedTools] = useState(0)

  const fetchConfig = async () => {
    try {
      setLoading(true)
      const res = await fetch(`${getApiBaseUrl()}/api/mcp/config`)
      if (!res.ok) throw new Error('Failed to fetch config')
      const data = await res.json()
      setEnabled(data.enabled)
      setConfig(JSON.stringify(data.servers, null, 2))
      setLoadedTools(data.loaded_tools || 0)
    } catch (e) {
      console.error(e)
      toast.error('Failed to load MCP config')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      fetchConfig()
    }
  }, [open])

  const handleSave = async () => {
    try {
      setLoading(true)
      // Validate JSON
      let parsedServers = {}
      try {
        parsedServers = JSON.parse(config)
      } catch (e) {
        toast.error('Invalid JSON configuration')
        setLoading(false)
        return
      }

      const res = await fetch(`${getApiBaseUrl()}/api/mcp/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enable: enabled,
          servers: parsedServers
        })
      })

      if (!res.ok) throw new Error('Failed to save config')
      
      const data = await res.json()
      setLoadedTools(data.loaded_tools || 0)
      toast.success(data.message || 'Configuration saved')
      setOpen(false)
    } catch (e) {
      console.error(e)
      toast.error('Failed to save MCP config')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="MCP Configuration" title="MCP Configuration">
            <Plug className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        </Button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[85dvh] flex-col gap-0 overflow-hidden p-0 sm:max-w-[600px]">
        <DialogHeader className="shrink-0 border-b border-border/80 px-6 py-4 pr-12">
          <DialogTitle className="flex items-center gap-2">
            <Plug className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            MCP Configuration
          </DialogTitle>
          <DialogDescription>
            Configure Model Context Protocol servers to extend capabilities.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border/80 bg-surface-subtle/70 p-3">
            <div className="space-y-0.5">
               <Label htmlFor="mcp-enabled" className="text-sm font-medium">Enable MCP</Label>
               <div className="text-sm text-muted-foreground">
                  {enabled ? 'MCP is currently active.' : 'MCP is disabled.'}
               </div>
            </div>
            <Switch
              id="mcp-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="mcp-config">Servers Configuration (JSON)</Label>
            <Textarea
              id="mcp-config"
              value={config}
              onChange={(e) => setConfig(e.target.value)}
              className="font-mono text-xs min-h-[200px]"
              placeholder='{ "server-name": { "command": "...", "args": [...] } }'
            />
            <p className="text-xs text-muted-foreground">
              Define servers with transport, command, and args.
            </p>
          </div>
          
          <div role="status" className="flex items-center gap-2 rounded-md border border-border/60 bg-surface-subtle/60 px-3 py-2 text-xs text-muted-foreground">
             {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className={cn('h-3.5 w-3.5', enabled && 'text-success')} />}
             <span>Loaded Tools: <span className="font-medium tabular-nums text-foreground">{loadedTools}</span></span>
          </div>
        </div>

        <DialogFooter className="shrink-0 border-t border-border/80 bg-surface-subtle/50 px-6 py-3.5">
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={loading}>
            {loading && <RefreshCw className="mr-2 h-4 w-4 animate-spin" />}
            Save & Reload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
