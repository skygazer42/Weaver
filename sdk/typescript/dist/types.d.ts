export type StreamEvent = {
    type: string;
    data: unknown;
};
export type SseEvent = {
    id?: number;
    event?: string;
    data?: unknown;
};
