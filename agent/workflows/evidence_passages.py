from __future__ import annotations

import re
from typing import Dict, List, Tuple


_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


def _paragraph_spans(text: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    if not text:
        return spans

    prev = 0
    for m in re.finditer(r"\n\s*\n+", text):
        end = m.start()
        if end > prev and text[prev:end].strip():
            spans.append((prev, end))
        prev = m.end()

    if prev < len(text) and text[prev:].strip():
        spans.append((prev, len(text)))
    return spans


def split_into_passages(text: str, *, max_chars: int = 1200) -> List[Dict[str, object]]:
    """
    Split a long text into passages with stable character offsets.

    Returns a list of dicts:
      - text: str
      - start_char: int (inclusive)
      - end_char: int (exclusive)
    """
    if not text:
        return []

    try:
        budget = int(max_chars)
    except Exception:
        budget = 0
    if budget <= 0:
        return []

    passages: List[Dict[str, object]] = []
    spans = _paragraph_spans(text)
    if not spans:
        spans = [(0, len(text))]

    chunk_start: int | None = None
    chunk_end: int | None = None
    chunk_heading: str | None = None
    current_heading: str | None = None

    def flush() -> None:
        nonlocal chunk_start, chunk_end, chunk_heading
        if chunk_start is None or chunk_end is None:
            return
        snippet = text[chunk_start:chunk_end]
        if snippet.strip():
            item: Dict[str, object] = {"text": snippet, "start_char": chunk_start, "end_char": chunk_end}
            if chunk_heading:
                item["heading"] = chunk_heading
            passages.append(item)
        chunk_start = None
        chunk_end = None
        chunk_heading = None

    for start, end in spans:
        span_len = end - start
        if span_len <= 0:
            continue

        paragraph = text[start:end]
        heading = _extract_markdown_heading(paragraph)
        if heading:
            flush()
            current_heading = heading
            chunk_start = start
            chunk_end = end
            chunk_heading = heading
            continue

        if span_len > budget:
            flush()
            for sub_start in range(start, end, budget):
                sub_end = min(sub_start + budget, end)
                snippet = text[sub_start:sub_end]
                if snippet.strip():
                    item: Dict[str, object] = {
                        "text": snippet,
                        "start_char": sub_start,
                        "end_char": sub_end,
                    }
                    if current_heading:
                        item["heading"] = current_heading
                    passages.append(item)
            continue

        if chunk_start is None:
            chunk_start = start
            chunk_end = end
            chunk_heading = current_heading
            continue

        assert chunk_end is not None
        if end - chunk_start <= budget:
            chunk_end = end
            continue

        flush()
        chunk_start = start
        chunk_end = end
        chunk_heading = current_heading

    flush()
    return passages


def _extract_markdown_heading(paragraph: str) -> str:
    if not paragraph:
        return ""
    match = _MARKDOWN_HEADING_RE.match(paragraph.strip())
    if not match:
        return ""
    return str(match.group(1) or "").strip()
