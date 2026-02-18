import type { SseEvent, StreamEvent } from './types.js';
export declare function parseSseFrame(frame: string): SseEvent | null;
export declare function readSseEvents(response: Response): AsyncGenerator<SseEvent>;
export declare function readDataStreamEvents(response: Response): AsyncGenerator<StreamEvent>;
