import { readDataStreamEvents, readSseEvents } from './sse.js';
export class WeaverApiError extends Error {
    status;
    path;
    bodyText;
    constructor(opts) {
        const suffix = opts.bodyText ? `: ${opts.bodyText}` : '';
        super(`Weaver API request failed (${opts.status}) ${opts.path}${suffix}`);
        this.status = opts.status;
        this.path = opts.path;
        this.bodyText = opts.bodyText;
    }
}
function normalizeBaseUrl(raw) {
    const text = String(raw || '').trim();
    if (!text)
        return 'http://127.0.0.1:8001';
    return text.replace(/\/+$/, '');
}
function mergeHeaders(headers, defaults) {
    const merged = new Headers(headers);
    for (const [key, value] of Object.entries(defaults)) {
        if (!merged.has(key))
            merged.set(key, value);
    }
    return merged;
}
export class WeaverClient {
    baseUrl;
    headers;
    fetchImpl;
    lastThreadId = null;
    constructor(opts = {}) {
        this.baseUrl = normalizeBaseUrl(opts.baseUrl || 'http://127.0.0.1:8001');
        this.headers = opts.headers || {};
        this.fetchImpl = opts.fetch || fetch;
    }
    url(path) {
        const p = path.startsWith('/') ? path : `/${path}`;
        return `${this.baseUrl}${p}`;
    }
    async requestJson(path, init = {}) {
        const response = await this.fetchImpl(this.url(path), {
            ...init,
            headers: mergeHeaders({ ...this.headers, ...(init.headers || {}) }, {
                Accept: 'application/json',
            }),
        });
        const bodyText = await response.text().catch(() => '');
        if (!response.ok) {
            throw new WeaverApiError({ status: response.status, path, bodyText });
        }
        if (!bodyText)
            return undefined;
        try {
            return JSON.parse(bodyText);
        }
        catch {
            return bodyText;
        }
    }
    async requestRaw(path, init = {}) {
        const response = await this.fetchImpl(this.url(path), {
            ...init,
            headers: mergeHeaders({ ...this.headers, ...(init.headers || {}) }, {}),
        });
        if (!response.ok) {
            const bodyText = await response.text().catch(() => '');
            throw new WeaverApiError({ status: response.status, path, bodyText });
        }
        return response;
    }
    async *chatSse(payload, opts = {}) {
        const response = await this.fetchImpl(this.url('/api/chat/sse'), {
            method: 'POST',
            headers: mergeHeaders({ ...this.headers }, {
                Accept: 'text/event-stream',
                'Content-Type': 'application/json',
            }),
            body: JSON.stringify({ ...payload, stream: payload.stream ?? true }),
            signal: opts.signal,
        });
        if (!response.ok) {
            const bodyText = await response.text().catch(() => '');
            throw new WeaverApiError({ status: response.status, path: '/api/chat/sse', bodyText });
        }
        this.lastThreadId =
            response.headers.get('X-Thread-ID') || response.headers.get('x-thread-id') || null;
        for await (const event of readSseEvents(response)) {
            const data = event.data;
            if (data && typeof data === 'object' && 'type' in data && 'data' in data) {
                yield data;
                continue;
            }
            if (event.event) {
                yield { type: event.event, data };
            }
        }
    }
    async cancelChat(threadId, request = undefined) {
        const safeId = encodeURIComponent(String(threadId));
        if (request) {
            return this.requestJson(`/api/chat/cancel/${safeId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(request),
            });
        }
        return this.requestJson(`/api/chat/cancel/${safeId}`, { method: 'POST' });
    }
    async cancelAllChats() {
        return this.requestJson('/api/chat/cancel-all', { method: 'POST' });
    }
    async *researchStream(query, opts = {}) {
        const params = new URLSearchParams({ query: String(query || '') });
        const path = `/api/research?${params.toString()}`;
        const response = await this.requestRaw(path, {
            method: 'POST',
            headers: { Accept: 'text/event-stream' },
            signal: opts.signal,
        });
        for await (const ev of readDataStreamEvents(response)) {
            yield ev;
        }
    }
    async listSessions(opts = {}) {
        const params = new URLSearchParams();
        if (opts.limit != null)
            params.set('limit', String(opts.limit));
        if (opts.status)
            params.set('status', String(opts.status));
        const query = params.toString();
        const path = query ? `/api/sessions?${query}` : '/api/sessions';
        return this.requestJson(path);
    }
    async getSession(threadId) {
        const safeId = encodeURIComponent(String(threadId));
        return this.requestJson(`/api/sessions/${safeId}`);
    }
    async getEvidence(threadId) {
        const safeId = encodeURIComponent(String(threadId));
        return this.requestJson(`/api/sessions/${safeId}/evidence`);
    }
    async listExportTemplates() {
        return this.requestJson('/api/export/templates');
    }
    async exportReport(threadId, opts = {}) {
        const safeId = encodeURIComponent(String(threadId));
        const params = new URLSearchParams();
        if (opts.format)
            params.set('format', String(opts.format));
        if (opts.title)
            params.set('title', String(opts.title));
        if (opts.template)
            params.set('template', String(opts.template));
        const query = params.toString();
        const path = query ? `/api/export/${safeId}?${query}` : `/api/export/${safeId}`;
        const response = await this.requestRaw(path, { method: 'GET' });
        return {
            contentType: response.headers.get('content-type'),
            bytes: await response.arrayBuffer(),
        };
    }
}
