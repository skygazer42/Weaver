'use client'

import React, { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { Settings, Server, RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react'

export function McpConfigDialog() {
  const [open, setOpen] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [config, setConfig] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadedTools, setLoadedTools] = useState(0)

  const fetchConfig = async () => {
    try {
      setLoading(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/mcp/config`)
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

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/mcp/config`, {
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
        <Button variant="ghost" size="icon" className="rounded-full hover:bg-muted/50" title="MCP Settings">
            <Settings className="h-5 w-5 text-muted-foreground" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            MCP Configuration
          </DialogTitle>
          <DialogDescription>
            Configure Model Context Protocol servers to extend capabilities.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 py-4">
          <div className="flex items-center justify-between space-x-2 border p-4 rounded-lg bg-muted/20">
            <div className="space-y-0.5">
               <Label className="text-base font-medium">Enable MCP</Label>
               <div className="text-sm text-muted-foreground">
                  {enabled ? 'MCP is currently active.' : 'MCP is disabled.'}
               </div>
            </div>
            <Switch
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </div>

          <div className="space-y-2">
            <Label>Servers Configuration (JSON)</Label>
            <Textarea
              value={config}
              onChange={(e) => setConfig(e.target.value)}
              className="font-mono text-xs min-h-[200px]"
              placeholder='{ "server-name": { "command": "...", "args": [...] } }'
            />
            <p className="text-xs text-muted-foreground">
              Define servers with transport, command, and args.
            </p>
          </div>
          
          <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/30 p-2 rounded">
             {loading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3 text-green-500" />}
             <span>Loaded Tools: {loadedTools}</span>
          </div>
        </div>

        <DialogFooter>
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
