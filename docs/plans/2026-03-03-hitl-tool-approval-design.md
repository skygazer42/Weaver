# HITL Tool Approval (Approve / Reject / Edit) — Design

Date: 2026-03-03

## Context

Weaver uses LangChain’s official `HumanInTheLoopMiddleware` to gate execution of
high-impact tools (`settings.tool_approval=true`). When gated tool calls are
detected, the middleware triggers a LangGraph `interrupt()` with a request
payload describing the requested actions.

The frontend already listens for `event: interrupt` on the SSE stream, but the
UI was previously limited to “Approve & Continue” and sent a legacy resume
payload shape (`{tool_approved, tool_calls}`) that does not match the official
middleware resume schema.

## Goals

- Show the user *which* tool calls are pending approval (tool name + args).
- Allow the user to:
  - **Approve** tool execution (continue).
  - **Reject** tool execution (continue without running tools, and allow the model
    to respond to the rejection).
  - **Edit** tool arguments before execution.
- Resume execution using the **official** HITL response payload (`decisions`),
  while remaining backward-compatible with legacy clients.

## Non-goals

- Full “report editing” UI for non-tool interrupts (e.g. `human_review_node`).
- Persisting edited tool call history beyond the current interrupt.
- Per-tool JSON-schema validation (future enhancement: use `args_schema`).

## Data Contract

### Interrupt (server → client)

The SSE `interrupt` event includes `prompts: [...]` (serialized LangGraph
interrupt values). For tool approval, the prompt is a HITL request:

- `action_requests[]`: `{ name, args, description? }`
- `review_configs[]`: `{ action_name, allowed_decisions[], args_schema? }`

### Resume (client → server)

To resume tool approval interrupts, the client sends:

```json
{
  "payload": {
    "decisions": [
      { "type": "approve" },
      { "type": "edit", "edited_action": { "name": "browser_search", "args": { "query": "..." } } },
      { "type": "reject", "message": "Optional reason" }
    ]
  }
}
```

The decision list must match `action_requests[]` length and order.

## Backend Changes

- Keep `POST /api/interrupt/resume` stable, but normalize legacy payloads:
  - Legacy `{tool_approved, tool_calls}` is translated into `{decisions:[...]}`.
- Pass the normalized payload into `Command(resume=...)` for LangGraph.
- Return either:
  - `ChatResponse` on completion, or
  - `{status:"interrupted", interrupts:[...]}` if the graph interrupts again.

## Frontend Changes

- Enhance the interrupt banner:
  - Render pending tool calls (`action_requests`) with an args preview.
  - Add an “Edit args” mode (JSON textarea per tool call).
  - Add a “Reject” action.
- Update resume calls to send the official `decisions` payload.
- Handle “interrupt again” responses by re-populating `pendingInterrupt` instead
  of clearing it.

## Error Handling

- Invalid JSON in “Edit args” blocks resume and surfaces an inline error.
- Resume network/API errors keep the interrupt visible so users can retry.

## Testing

- Backend unit tests for legacy→official resume payload normalization.
- Frontend unit tests for building decision arrays from HITL requests.
- Existing smoke tests continue to validate 404 behavior for unknown threads.

