"""
Shared parsing utilities for Weaver workflows.

Consolidates duplicated parsing functions from deepsearch and other modules.
"""

import ast
import re
import textwrap
from typing import Any, Dict, List


def parse_list_output(text: str) -> List[str]:
    """
    Parse python-list-like output into a string list.

    Handles:
    - Code fenced lists (```python ... ```)
    - Raw Python list literals
    - Fallback to line-by-line parsing

    Args:
        text: Raw text output from LLM

    Returns:
        List of parsed strings
    """
    if not text:
        return []

    # Extract from code fence if present
    fenced = re.findall(r"```(?:python)?(.*?)```", text, flags=re.S | re.I)
    if fenced:
        text = fenced[-1]

    # Try to find list brackets
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        text = text[start : end + 1]

    # Try ast.literal_eval (safe evaluation)
    try:
        data = ast.literal_eval(text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if isinstance(x, (str, int, float))]
    except Exception:
        pass

    # Fallback: split by newline
    return [line.strip() for line in text.splitlines() if line.strip()]


def format_search_results(results: List[Dict[str, Any]]) -> str:
    """
    Format search results for prompt consumption.

    Args:
        results: List of search result dictionaries

    Returns:
        Formatted string with numbered results
    """
    blocks: List[str] = []
    for idx, r in enumerate(results, 1):
        blocks.append(
            textwrap.dedent(
                f"""\
                [{idx}]
                标题: {r.get("title") or "N/A"}
                日期: {r.get("published_date") or "unknown"}
                评分: {r.get("score", 0)}
                链接: {r.get("url") or ""}
                摘要: {r.get("summary") or r.get("snippet") or ""}
                原文: {(r.get("raw_excerpt") or "")[:500]}
                """
            ).strip()
        )
    return "\n\n".join(blocks)


def extract_response_content(response: Any) -> str:
    """
    Safely extract content from LLM response.

    Args:
        response: LLM response object

    Returns:
        Content string or empty string if not found
    """
    return getattr(response, "content", "") or ""


def parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract and parse JSON from text that may contain markdown code fences.

    Args:
        text: Text potentially containing JSON

    Returns:
        Parsed JSON dict or empty dict on failure
    """
    import json

    if not text:
        return {}

    # Try to extract from code fence
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if json_match:
        text = json_match.group(1)

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
