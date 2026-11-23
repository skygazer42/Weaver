'use client'

import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { workspaceRequest } from '@/lib/workspace'

type ArtifactState = { error: string } | { report: string; reportUrl: string; chartUrl: string }

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
      <div className="space-y-3">
        <p role="alert" className="text-sm text-destructive">{artifacts.error}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => {
          setArtifacts(null)
          setAttempt((current) => current + 1)
        }}>Retry loading artifacts</Button>
      </div>
    )
  }

  return (
    <div className="space-y-7">
      <section aria-labelledby="workspace-chart-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="workspace-chart-heading" className="font-semibold">Chart</h3>
          <Button variant="outline" size="sm" asChild>
            <a href={artifacts.chartUrl} download="chart.svg" className="gap-2"><Download className="h-4 w-4" aria-hidden="true" />Download chart</a>
          </Button>
        </div>
        <div className="overflow-hidden rounded-md border bg-white">
          <img src={artifacts.chartUrl} alt="Chart generated from the CSV" className="h-auto w-full" />
        </div>
      </section>
      <section aria-labelledby="workspace-report-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="workspace-report-heading" className="font-semibold">Report</h3>
          <Button variant="outline" size="sm" asChild>
            <a href={artifacts.reportUrl} download="report.md" className="gap-2"><Download className="h-4 w-4" aria-hidden="true" />Download Markdown</a>
          </Button>
        </div>
        <div className="overflow-x-auto break-words rounded-md border bg-background px-4 py-3 text-sm leading-relaxed [&_a]:underline [&_h1]:my-3 [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:my-2 [&_h3]:font-semibold [&_ol]:ml-5 [&_ol]:list-decimal [&_p]:my-2 [&_pre]:overflow-x-auto [&_table]:my-3 [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:bg-muted [&_th]:p-2 [&_ul]:ml-5 [&_ul]:list-disc">
          <ReactMarkdown remarkPlugins={[remarkGfm]} disallowedElements={['img']}>{artifacts.report}</ReactMarkdown>
        </div>
      </section>
    </div>
  )
}
