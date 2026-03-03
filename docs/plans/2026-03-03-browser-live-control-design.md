# Browser Live View “Real Control” (WS Input) — Design

## Goal

Make Weaver’s existing browser live stream (`/api/browser/{thread_id}/stream`) feel like a real remote browser:

- Continuous frames (already via CDP screencast / screenshot fallback)
- **Interactive control** from the frontend: click / move / scroll / keyboard / navigate
- Observable acknowledgements so e2e + users can tell an action actually executed

This is **not** a mock: inputs are applied to the same Playwright page used for streaming (sandbox/E2B).

## Non‑Goals

- Audio streaming
- High-efficiency video codecs (H264/WebRTC). We keep JPEG frames over WS.
- Multi-tab management UI
- Full IME/composition fidelity (we’ll support `press` + basic `type`)

## Protocol (WebSocket)

Existing incoming actions remain:

- `{"action":"start","quality":70,"max_fps":10}`
- `{"action":"stop"}`
- `{"action":"capture","quality":70}`

Add new incoming input actions (all optional `id` for correlation):

### Mouse

```json
{"action":"mouse","type":"click","x":0.52,"y":0.31,"button":"left","clicks":1,"id":"..."}
{"action":"mouse","type":"move","x":0.52,"y":0.31,"id":"..."}
{"action":"mouse","type":"down","button":"left","id":"..."}
{"action":"mouse","type":"up","button":"left","id":"..."}
```

- `x`,`y` are **normalized** coordinates in `[0..1]` relative to the current viewport.

### Scroll / Wheel

```json
{"action":"scroll","dx":0,"dy":240,"id":"..."}
```

### Keyboard

```json
{"action":"keyboard","type":"press","key":"Enter","id":"..."}
{"action":"keyboard","type":"type","text":"hello","id":"..."}
```

### Navigate

```json
{"action":"navigate","url":"https://example.com","id":"..."}
```

Outgoing messages add a new `ack` type (in addition to existing `status`/`frame`/`error`):

```json
{"type":"ack","id":"...","ok":true,"action":"mouse","timestamp":1710000000.0,"metadata":{"url":"...","title":"..."}}
{"type":"ack","id":"...","ok":false,"action":"navigate","error":"..."}
```

## Backend Implementation

- Extend the WS loop in `main.py` to recognize the new `action` values.
- Execute Playwright calls using `sandbox_browser_sessions.run_async(thread_id, fn)` to preserve thread-affinity.
- Map normalized coordinates → pixels using (in order):
  1) `page.viewport_size` if available, else
  2) `page.evaluate(() => ({w: window.innerWidth, h: window.innerHeight}))`
- Always return an `ack` for any parsed input action (success or error). Include best-effort `url`/`title`.
- Validate URLs for `navigate` (only allow `http://` and `https://`).

## Frontend Implementation

- Add a **Control** toggle in `BrowserViewer` (default OFF).
- When enabled:
  - Click on the live frame sends a `mouse.click` with normalized coords.
  - Wheel sends `scroll` events.
  - When the viewer is focused, `keydown` sends `keyboard.press` (and basic `type` for printable chars).
  - Optional small URL input in the viewer chrome sends `navigate` on Enter.
- Extend `useBrowserStream` to expose `sendInput()` helpers and to surface `ack` status (for UI + tests).

## Testing

- Backend unit tests (FastAPI `TestClient` WS):
  - send `mouse.click`/`scroll`/`keyboard.press`/`navigate` and assert `ack` + that the fake page received calls
- Frontend Playwright e2e:
  - enable Control
  - navigate to `https://example.com`
  - assert BrowserViewer address bar updates based on streamed `metadata.url`

