import { useState, useEffect, useRef } from 'react'
import type { MarkdownWorkerData, MarkdownWorkerResult } from '../lib/workers/markdown.worker'

interface UseMarkdownWorkerReturn {
    processedContent: string
    citations: string[]
    hasMermaid: boolean
    isProcessing: boolean
}

export function useMarkdownWorker(content: string, enabled: boolean = true): UseMarkdownWorkerReturn {
    const [result, setResult] = useState<MarkdownWorkerResult>({
        processedContent: content, // Default to original
        citations: [],
        hasMermaid: false,
        isHeavy: false
    })
    const [isProcessing, setIsProcessing] = useState(false)
    const workerRef = useRef<Worker | null>(null)

    useEffect(() => {
        if (!enabled || !content) {
            setResult(prev => ({ ...prev, processedContent: content }))
            return
        }

        // Only use worker for longer content to avoid overhead, unless enabled force
        // But Plan said > 2000 chars. We can implement that check inside component or here.
        // We'll process everything if enabled, as regex can be slow on 500 chars too if frequent.
        // Actually, worker overhead is ~50ms.

        setIsProcessing(true)

        if (!workerRef.current) {
            workerRef.current = new Worker(new URL('../lib/workers/markdown.worker.ts', import.meta.url))
        }

        const worker = workerRef.current

        const handleMessage = (e: MessageEvent<MarkdownWorkerResult>) => {
            setResult(e.data)
            setIsProcessing(false)
        }

        worker.onmessage = handleMessage
        worker.postMessage({ content })

        return () => {
            // Don't terminate aggressivey to allow reuse, 
            // but strictly cleaning up listener is good.
            // We keep the worker instance alive via ref for component lifecycle.
            worker.onmessage = null
        }
    }, [content, enabled])

    return {
        ...result,
        isProcessing
    }
}
