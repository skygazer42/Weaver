import type { StreamEvent } from './types.js';
export declare class WeaverApiError extends Error {
    status: number;
    path: string;
    bodyText: string;
    constructor(opts: {
        status: number;
        path: string;
        bodyText: string;
    });
}
type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export declare class WeaverClient {
    private baseUrl;
    private headers;
    private fetchImpl;
    lastThreadId: string | null;
    constructor(opts?: {
        baseUrl?: string;
        headers?: Record<string, string>;
        fetch?: FetchLike;
    });
    private url;
    requestJson<T>(path: string, init?: RequestInit): Promise<T>;
    requestRaw(path: string, init?: RequestInit): Promise<Response>;
    chatSse(payload: unknown, opts?: {
        signal?: AbortSignal;
    }): AsyncGenerator<StreamEvent>;
    cancelChat(threadId: string): Promise<unknown>;
    cancelAllChats(): Promise<unknown>;
    researchStream(query: string, opts?: {
        signal?: AbortSignal;
    }): AsyncGenerator<StreamEvent>;
    listSessions(opts?: {
        limit?: number;
        status?: string;
    }): Promise<unknown>;
    getSession(threadId: string): Promise<unknown>;
    getEvidence(threadId: string): Promise<unknown>;
    listExportTemplates(): Promise<unknown>;
    exportReport(threadId: string, opts?: {
        format?: string;
        title?: string;
        template?: string;
    }): Promise<{
        contentType: string | null;
        bytes: ArrayBuffer;
    }>;
}
export {};
