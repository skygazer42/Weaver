"""Deepsearch prompt templates (ported)."""

from .behavior import get_behavior_prompt
from .prompt_lang import (
    final_summary_prompt,
    formulate_query_prompt,
    related_url_prompt,
    summary_crawl_prompt,
    summary_text_prompt,
)

__all__ = [
    "formulate_query_prompt",
    "related_url_prompt",
    "summary_crawl_prompt",
    "final_summary_prompt",
    "summary_text_prompt",
    "get_behavior_prompt",
]
