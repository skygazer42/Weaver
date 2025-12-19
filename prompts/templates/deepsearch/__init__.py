"""Deepsearch prompt templates (ported)."""

from .prompt_lang import (
    formulate_query_prompt,
    related_url_prompt,
    summary_crawl_prompt,
    final_summary_prompt,
    summary_text_prompt,
)

__all__ = [
    "formulate_query_prompt",
    "related_url_prompt",
    "summary_crawl_prompt",
    "final_summary_prompt",
    "summary_text_prompt",
]
