# Deepsearch Latency Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `deep research` return sooner for ordinary questions and surface progress events while deepsearch work is still running.

**Architecture:** Tighten `auto` deepsearch mode so it prefers the linear runner for simple prompts and reserves tree exploration for clearly broad research topics. In parallel, make deepsearch emit incremental search events during tree exploration and update the SSE stream loop so queued tool/research events flush even while a long-running graph node is still executing.

**Tech Stack:** Python, FastAPI, LangGraph streaming, pytest

---

### Task 1: Lock in mode-selection regression tests

**Files:**
- Modify: `tests/test_deepsearch_mode_selection.py`
- Test: `tests/test_deepsearch_mode_selection.py`

**Step 1: Write the failing test**

Add a test proving `run_deepsearch_auto()` chooses the linear runner for a short factual query when `deepsearch_mode=auto` and tree exploration remains globally enabled.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_deepsearch_mode_selection.py -k simple_query -q`

Expected: FAIL because `auto` still routes the simple query to tree mode.

**Step 3: Write minimal implementation**

Add a simple-query heuristic inside `agent/workflows/deepsearch_optimized.py` and use it in `run_deepsearch_auto()`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_deepsearch_mode_selection.py -k simple_query -q`

Expected: PASS

### Task 2: Lock in stream queue flushing regression test

**Files:**
- Modify: `tests/test_chat_sse_quality_events.py`
- Test: `tests/test_chat_sse_quality_events.py`

**Step 1: Write the failing test**

Add an SSE test that injects a queued `quality_update` before the graph yields its next event and proves `/api/chat/sse` flushes it before the final completion.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_chat_sse_quality_events.py -k flushes_queued_quality_update -q`

Expected: FAIL because the current stream loop only drains queued events when a graph event arrives.

**Step 3: Write minimal implementation**

Refactor the SSE loop in `main.py` so it periodically drains the internal queue while awaiting the next graph event.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_sse_quality_events.py -k flushes_queued_quality_update -q`

Expected: PASS

### Task 3: Emit tree progress incrementally

**Files:**
- Modify: `agent/workflows/deepsearch_optimized.py`
- Test: `tests/test_deepsearch_quality_diagnostics.py`

**Step 1: Write the failing test**

Add a focused test showing tree mode emits `search` progress as each search call completes instead of batching everything at the end.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_deepsearch_quality_diagnostics.py -k incremental_tree_search -q`

Expected: FAIL because tree mode currently emits `search` events only after the tree finishes.

**Step 3: Write minimal implementation**

Wrap the tree search function so every search call emits a compact `search` event immediately after results return.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_deepsearch_quality_diagnostics.py -k incremental_tree_search -q`

Expected: PASS

### Task 4: Run regression coverage

**Files:**
- Test: `tests/test_deepsearch_mode_selection.py`
- Test: `tests/test_chat_sse_quality_events.py`
- Test: `tests/test_deepsearch_quality_diagnostics.py`

**Step 1: Run targeted regression suite**

Run: `pytest tests/test_deepsearch_mode_selection.py tests/test_chat_sse_quality_events.py tests/test_deepsearch_quality_diagnostics.py -q`

Expected: PASS

**Step 2: Run broader smoke coverage**

Run: `pytest tests/test_chat_sources_event.py tests/test_chat_stream_main_answer_clean.py tests/test_sse_format.py -q`

Expected: PASS

### Task 5: Finish the session cleanly

**Files:**
- Verify: git history / remote sync

**Step 1: Commit**

Run: `git add ... && git commit -m "fix: reduce deepsearch latency"`

**Step 2: Rebase and push**

Run: `git pull --rebase && git push`

**Step 3: Final verification**

Run: `git status`

Expected: branch up to date with origin and clean.
