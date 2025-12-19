'use client'

import React from 'react'
import { FolderOpen, FileText, Image as ImageIcon, Code, Clock } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'

export function Library() {
  return (
    <div className="flex-1 h-full overflow-hidden flex flex-col p-6 md:p-10">
      <div className="max-w-4xl mx-auto w-full h-full flex flex-col">
        <div className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FolderOpen className="h-8 w-8 text-primary" />
            Library
          </h1>
          <p className="text-muted-foreground mt-2 text-lg">
            Manage your saved artifacts, reports, and generated files.
          </p>
        </div>

        <div className="grid grid-cols-4 gap-4 mb-8">
            <StatsCard label="Documents" value="12" icon={FileText} />
            <StatsCard label="Images" value="48" icon={ImageIcon} />
            <StatsCard label="Code Snippets" value="24" icon={Code} />
            <StatsCard label="Total Size" value="15MB" icon={FolderOpen} />
        </div>

        <div className="flex-1 border rounded-xl bg-card overflow-hidden flex flex-col">
            <div className="p-4 border-b bg-muted/30 font-medium text-sm grid grid-cols-12 text-muted-foreground">
                <div className="col-span-6">Name</div>
                <div className="col-span-3">Type</div>
                <div className="col-span-3 text-right">Date</div>
            </div>
            <ScrollArea className="flex-1">
                <div className="divide-y">
                   {[1,2,3,4,5].map(i => (
                       <div key={i} className="p-4 grid grid-cols-12 text-sm hover:bg-muted/50 transition-colors items-center">
                           <div className="col-span-6 flex items-center gap-3 font-medium">
                               <FileText className="h-4 w-4 text-blue-500" />
                               Report_Analysis_{2024+i}.pdf
                           </div>
                           <div className="col-span-3 text-muted-foreground">PDF Document</div>
                           <div className="col-span-3 text-right text-muted-foreground flex items-center justify-end gap-1">
                               <Clock className="h-3 w-3" /> 2 days ago
                           </div>
                       </div>
                   ))}
                </div>
            </ScrollArea>
        </div>
      </div>
    </div>
  )
}

function StatsCard({ label, value, icon: Icon }: any) {
    return (
        <div className="p-4 rounded-xl border bg-card flex flex-col gap-2">
            <Icon className="h-5 w-5 text-muted-foreground" />
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-xs text-muted-foreground">{label}</div>
        </div>
    )
}
