'use client'

import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { getArtifactDownloadUrl } from '@/lib/api'
import { workspaceRequest } from '@/lib/workspace'

type ArtifactState = { error: string } | { report: string; reportUrl: string; chartUrl: string }

export function WorkspaceMarkdown({ content }: { content: string }) {
  return (
    <div className="prose min-w-0 rounded-lg border border-border/80 bg-card p-5 sm:p-6">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ table: ({ children }) => <table className="whitespace-nowrap">{children}</table> }}
        disallowedElements={['img']}
        urlTransform={(url) => url.startsWith('/api/workspaces/') ? getArtifactDownloadUrl(url) ?? '' : defaultUrlTransform(url)}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export function WorkspaceArtifacts({ url }: { url: string }) {
  const [artifacts, setArtifacts] = useState<ArtifactState | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const options = { signal: controller.signal }
    const objectUrls: string[] = []

    async function loadArtifacts() {
      try {
        const [reportBlob, chartBlob] = await Promise.all([
          workspaceRequest(`${url}/report.md`, options).then((res) => res.blob()),
          workspaceRequest(`${url}/chart.svg`, options).then((res) => res.blob()),
        ])
        const report = await reportBlob.text()
        if (controller.signal.aborted) return
        const reportUrl = URL.createObjectURL(reportBlob)
        const chartUrl = URL.createObjectURL(chartBlob)
        objectUrls.push(reportUrl, chartUrl)
        setArtifacts({ report, reportUrl, chartUrl })
      } catch (cause) {
        if (!controller.signal.aborted) {
          setArtifacts({ error: cause instanceof Error ? cause.message : 'Could not load the artifacts.' })
        }
      }
    }

    void loadArtifacts()
    return () => {
      controller.abort()
      objectUrls.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
    }
  }, [url, attempt])

  if (!artifacts) return <p role="status" className="text-sm text-muted-foreground">Loading report and chart…</p>
  if ('error' in artifacts) {
    return (
      <div className="space-y-3 rounded-lg border border-destructive-border bg-destructive-surface p-4">
        <p role="alert" className="break-words text-sm text-destructive">{artifacts.error}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => {
          setArtifacts(null)
          setAttempt((current) => current + 1)
        }}>Retry loading artifacts</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="workspace-chart-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 pb-3">
          <h3 id="workspace-chart-heading" className="text-sm font-semibold tracking-tight">Chart</h3>
          <Button variant="outline" size="sm" asChild>
            <a href={artifacts.chartUrl} download="chart.svg" className="gap-2"><Download className="h-4 w-4" aria-hidden="true" />Download chart</a>
          </Button>
        </div>
        <div className="rounded-lg border border-border/80 bg-white p-3 shadow-xs">
          <img src={artifacts.chartUrl} alt="Chart generated from the CSV" className="h-auto w-full" />
        </div>
      </section>
      <section aria-labelledby="workspace-report-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 pb-3">
          <h3 id="workspace-report-heading" className="text-sm font-semibold tracking-tight">Report</h3>
          <Button variant="outline" size="sm" asChild>
            <a href={artifacts.reportUrl} download="report.md" className="gap-2"><Download className="h-4 w-4" aria-hidden="true" />Download Markdown</a>
          </Button>
        </div>
        <WorkspaceMarkdown content={artifacts.report} />
      </section>
    </div>
  )
}
