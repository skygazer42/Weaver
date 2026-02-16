from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


@dataclass
class FetchedPage:
    url: str
    raw_url: str
    method: str
    text: Optional[str] = None
    title: Optional[str] = None
    published_date: Optional[str] = None
    retrieved_at: Optional[str] = None
    markdown: Optional[str] = None
    http_status: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": _json_safe(self.url),
            "raw_url": _json_safe(self.raw_url),
            "title": _json_safe(self.title),
            "published_date": _json_safe(self.published_date),
            "retrieved_at": _json_safe(self.retrieved_at),
            "method": _json_safe(self.method),
            "text": _json_safe(self.text),
            "markdown": _json_safe(self.markdown),
            "http_status": _json_safe(self.http_status),
            "error": _json_safe(self.error),
            "attempts": _json_safe(self.attempts),
        }
