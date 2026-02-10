/* eslint-disable no-restricted-globals */

// Define the worker interface
export interface MarkdownWorkerData {
    content: string
}

export interface MarkdownWorkerResult {
    processedContent: string
    citations: string[]
    hasMermaid: boolean
    isHeavy: boolean // > 2000 chars or many code blocks
}

// Helper to normalize LaTeX delimiters (moved from MessageItem.tsx)
const preprocessContent = (content: string): string => {
    if (!content) return ''
    return content
        .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$') // \( ... \) -> $ ... $
        .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$') // \[ ... \] -> $$ ... $$
}

// Extract citations [n]
const extractCitations = (content: string): string[] => {
    const matches = content.match(/\[\d+\]/g)
    return matches ? Array.from(new Set(matches)) : []
}

// Check for Mermaid
const checkMermaid = (content: string): boolean => {
    return /```mermaid/.test(content)
}

self.onmessage = (e: MessageEvent<MarkdownWorkerData>) => {
    const { content } = e.data

    if (!content) {
        self.postMessage({
            processedContent: '',
            citations: [],
            hasMermaid: false,
            isHeavy: false
        })
        return
    }

    const processedContent = preprocessContent(content)
    const citations = extractCitations(content)
    const hasMermaid = checkMermaid(content)
    const isHeavy = content.length > 2000 || (content.match(/```/g) || []).length > 6

    const result: MarkdownWorkerResult = {
        processedContent,
        citations,
        hasMermaid,
        isHeavy
    }

    self.postMessage(result)
}
