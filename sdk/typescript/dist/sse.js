export function parseSseFrame(frame) {
    const text = String(frame ?? '');
    if (!text.trim())
        return null;
    const lines = text.split('\n').map((l) => l.trimEnd());
    let eventName = '';
    let idText = '';
    const dataLines = [];
    for (const line of lines) {
        if (!line)
            continue;
        if (line.startsWith(':'))
            continue;
        if (line.startsWith('event:')) {
            eventName = line.slice('event:'.length).trim();
            continue;
        }
        if (line.startsWith('id:')) {
            idText = line.slice('id:'.length).trim();
            continue;
        }
        if (line.startsWith('data:')) {
            dataLines.push(line.slice('data:'.length).trimStart());
            continue;
        }
    }
    if (dataLines.length === 0)
        return null;
    const dataText = dataLines.join('\n');
    let parsed;
    try {
        parsed = JSON.parse(dataText);
    }
    catch {
        return null;
    }
    const out = { data: parsed };
    if (eventName)
        out.event = eventName;
    if (idText) {
        const idNum = Number(idText);
        if (Number.isFinite(idNum))
            out.id = idNum;
    }
    return out;
}
export async function* readSseEvents(response) {
    if (!response.body)
        return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done)
            break;
        buffer += decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r\n/g, '\n');
        const frames = buffer.split('\n\n');
        buffer = frames.pop() || '';
        for (const frame of frames) {
            const parsed = parseSseFrame(frame);
            if (parsed)
                yield parsed;
        }
    }
    const tail = buffer.trim();
    if (tail) {
        const parsed = parseSseFrame(tail);
        if (parsed)
            yield parsed;
    }
}
export async function* readDataStreamEvents(response) {
    if (!response.body)
        return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done)
            break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line)
                continue;
            if (!line.startsWith('0:'))
                continue;
            try {
                const parsed = JSON.parse(line.slice(2));
                if (parsed && typeof parsed === 'object' && 'type' in parsed && 'data' in parsed) {
                    yield parsed;
                }
            }
            catch {
                continue;
            }
        }
    }
    const tail = buffer.trim();
    if (tail.startsWith('0:')) {
        try {
            const parsed = JSON.parse(tail.slice(2));
            if (parsed && typeof parsed === 'object' && 'type' in parsed && 'data' in parsed) {
                yield parsed;
            }
        }
        catch {
            // ignore
        }
    }
}
