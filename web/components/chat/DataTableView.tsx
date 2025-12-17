'use client'

import React, { useMemo, useState } from 'react'
import Papa from 'papaparse'
import { Download, Table as TableIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

interface DataTableViewProps {
  data: string
  type: 'json' | 'csv'
}

export function DataTableView({ data, type }: DataTableViewProps) {
  const [page, setPage] = useState(0)
  const pageSize = 5

  const parsedData = useMemo(() => {
    try {
      if (type === 'json') {
        const json = JSON.parse(data)
        if (Array.isArray(json)) return json
        if (typeof json === 'object' && json !== null) return [json] // Single object
        return null
      } else {
        const result = Papa.parse(data, { header: true, skipEmptyLines: true })
        return result.data
      }
    } catch (e) {
      console.error('Failed to parse data', e)
      return null
    }
  }, [data, type])

  if (!parsedData || parsedData.length === 0) return null

  // Get headers from first row
  const headers = Object.keys(parsedData[0] as object)
  const rows = parsedData.slice(page * pageSize, (page + 1) * pageSize)
  const totalPages = Math.ceil(parsedData.length / pageSize)

  const handleDownload = () => {
      const blob = new Blob([data], { type: type === 'json' ? 'application/json' : 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `data.${type}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
  }

  return (
    <div className="my-4 rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden">
      <div className="flex items-center justify-between p-3 border-b bg-muted/30">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <TableIcon className="h-4 w-4" />
            <span>Data View ({parsedData.length} rows)</span>
        </div>
        <Button variant="ghost" size="sm" onClick={handleDownload} className="h-7 px-2">
            <Download className="h-3.5 w-3.5 mr-1" />
            Download
        </Button>
      </div>
      
      <ScrollArea className="w-full">
          <div className="w-full overflow-auto">
            <table className="w-full caption-bottom text-sm text-left">
                <thead className="[&_tr]:border-b">
                    <tr className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
                        {headers.map(header => (
                            <th key={header} className="h-10 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0 whitespace-nowrap">
                                {header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="[&_tr:last-child]:border-0">
                    {rows.map((row: any, i) => (
                        <tr key={i} className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
                            {headers.map(header => (
                                <td key={header} className="p-4 align-middle [&:has([role=checkbox])]:pr-0 whitespace-nowrap">
                                    {typeof row[header] === 'object' ? JSON.stringify(row[header]) : String(row[header])}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
          </div>
          <div className="flex items-center justify-end p-2 border-t gap-2">
              <span className="text-xs text-muted-foreground">
                  Page {page + 1} of {totalPages}
              </span>
              <div className="flex gap-1">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="h-7 px-2" 
                    disabled={page === 0}
                    onClick={() => setPage(p => p - 1)}
                  >
                      Prev
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="h-7 px-2" 
                    disabled={page >= totalPages - 1}
                    onClick={() => setPage(p => p + 1)}
                  >
                      Next
                  </Button>
              </div>
          </div>
      </ScrollArea>
    </div>
  )
}
