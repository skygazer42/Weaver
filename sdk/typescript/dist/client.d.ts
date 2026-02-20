import type { StreamEvent } from './types.js';
import type { components } from './openapi-types.js';
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
type ChatRequest = components['schemas']['ChatRequest'];
type CancelRequest = components['schemas']['CancelRequest'];
type ResearchRequest = components['schemas']['ResearchRequest'];
type SessionsListResponse = components['schemas']['SessionsListResponse'];
type EvidenceResponse = components['schemas']['EvidenceResponse'];
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
    chatSse(payload: Omit<ChatRequest, 'stream'> & {
        stream?: boolean;
    }, opts?: {
        signal?: AbortSignal;
    }): AsyncGenerator<StreamEvent>;
    cancelChat(threadId: string, request?: CancelRequest | undefined): Promise<unknown>;
    cancelAllChats(): Promise<unknown>;
    researchStream(query: string, opts?: {
        signal?: AbortSignal;
    }): AsyncGenerator<StreamEvent>;
    researchSse(payload: ResearchRequest, opts?: {
        signal?: AbortSignal;
    }): AsyncGenerator<StreamEvent>;
    listSessions(opts?: {
        limit?: number;
        status?: string;
    }): Promise<SessionsListResponse>;
    getSession(threadId: string): Promise<unknown>;
    getEvidence(threadId: string): Promise<EvidenceResponse>;
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
