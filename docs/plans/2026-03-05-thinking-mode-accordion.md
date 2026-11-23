# Thinking Mode (Process Accordion + Clean Final Answer) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `/api/chat` stream only the clean final answer into the main assistant message while exposing intermediate “process” (search queries, tool calls, browser screenshots, status) via structured events rendered in a minimal OpenAI/DeepSeek-style “Thinking…” accordion.

**Architecture:** Backend keeps emitting status/tool/search/screenshot events but stops forwarding intermediate node `output.messages` (planner/query-gen/etc) into the main message stream. Frontend parses these events into per-message `processEvents` and renders a single-line “Thinking…” trigger with a CSS Grid `0fr/1fr` accordion for details, hiding the empty assistant bubble while generation is in progress.

**Tech Stack:** FastAPI + LangGraph (`astream_events`), Vercel AI SDK data stream protocol (`0:{json}\n`), Next.js/React, Tailwind/shadcn tokens.

---

### Task 1: Backend — keep process events, stop intermediate text/messages in main answer

**Files:**
- Modify: `main.py`
- Test: `tests/test_chat_stream_main_answer_clean.py`

**Step 1: Write the failing test**

- Add a dummy `research_graph` that emits:
  - planner node start/end with `output.messages=["plan"]`
  - a streamed token from planner
  - writer node start + streamed token
  - graph end with `is_complete=True`, `final_report="final"`
- Assert:
  - no `type == "message"` chunks are emitted
  - planner `type=="text"` is not emitted
  - completion is emitted with `"final"`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_chat_stream_main_answer_clean.py -q`
Expected: FAIL because `stream_agent_events()` currently forwards `output.messages` and planner tokens.

**Step 3: Write minimal implementation**

- In `stream_agent_events()`:
  - Stop yielding `type:"message"` for `output.get("messages", ...)`.
  - Gate `type:"text"` emissions to only “final writing” nodes (e.g. `writer`, `direct_answer`, `agent`, `reviser`), never planner/search/deepsearch.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_stream_main_answer_clean.py -q`
Expected: PASS

**Step 5: Commit**

Run:
`git add main.py tests/test_chat_stream_main_answer_clean.py docs/plans/2026-03-05-thinking-mode-accordion.md`
`git commit -m "feat(stream): keep final answer clean; gate intermediate output"`

---

### Task 2: Frontend — minimal “Thinking…” accordion fed by process events

**Files:**
- Modify: `web/types/chat.ts`
- Modify: `web/hooks/useChatStream.ts`
- Modify: `web/components/chat/message/ThinkingProcess.tsx`
- Modify: `web/components/chat/MessageItem.tsx`

**Step 1: Update types**

- Add `processEvents` (raw stream events, capped) and optional `metrics`/timestamps to `Message`.

**Step 2: Parse process events in `useChatStream`**

- Keep main `content` updates only from `text` + `completion`.
- For `status`, `tool_start`, `tool_result`, `tool_error`, `search`, `screenshot`, `task_update`, `research_*`, `quality_update`, store into `assistantMessage.processEvents`.
- Handle `done` to store metrics (duration, event count) for the accordion header.
- Handle `error`/`cancelled` to avoid silent empty responses.

**Step 3: Replace Thinking UI with OpenAI-style line + CSS Grid accordion**

- A single trigger row:
  - spinner while streaming; checkmark when done
  - label: `Thinking…` / `Thought for 7s · 12 steps`
  - chevron rotates on expand
- Accordion content:
  - simple timeline list of process events (search queries, tools, screenshots)
  - animation: container `display: grid`, transition `grid-template-rows` between `0fr` and `1fr`
  - do not measure `scrollHeight`

**Step 4: Hide empty assistant bubble while thinking**

- If assistant `content` is empty and the message is still streaming, show only the Thinking line (no blank bubble).

**Step 5: Commit**

Run:
`git add web/types/chat.ts web/hooks/useChatStream.ts web/components/chat/message/ThinkingProcess.tsx web/components/chat/MessageItem.tsx`
`git commit -m "feat(web): OpenAI-style thinking accordion for process events"`

---

### Task 3: Quality gates + push

**Run:**
- `pytest -q`
- `pnpm -C web lint`
- (optional but recommended) `pnpm -C web build`

**Push:**
- `git pull --rebase`
- `git push`
- `git status` shows clean and up-to-date

