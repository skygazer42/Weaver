"""Loader for Deep Research benchmark JSONL datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BenchmarkTask:
    """Normalized benchmark task schema."""

    task_id: str
    query: str
    constraints: Dict[str, Any] = field(default_factory=dict)
    expected_fields: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.task_id,
            "query": self.query,
            "constraints": self.constraints,
            "expected_fields": self.expected_fields,
            "metadata": self.metadata,
        }


def _validate_task(raw: Dict[str, Any], line_number: int) -> BenchmarkTask:
    if not isinstance(raw, dict):
        raise ValueError(f"Line {line_number}: expected object")

    query = str(raw.get("query") or "").strip()
    if not query:
        raise ValueError(f"Line {line_number}: missing required field 'query'")

    expected_fields = raw.get("expected_fields")
    if not isinstance(expected_fields, list) or not all(
        isinstance(item, str) and item.strip() for item in expected_fields
    ):
        raise ValueError(
            f"Line {line_number}: 'expected_fields' must be a non-empty list of strings"
        )

    constraints = raw.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise ValueError(f"Line {line_number}: 'constraints' must be an object")

    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"Line {line_number}: 'metadata' must be an object")

    task_id = str(raw.get("id") or f"task_{line_number:03d}").strip()

    return BenchmarkTask(
        task_id=task_id,
        query=query,
        constraints=constraints,
        expected_fields=expected_fields,
        metadata=metadata,
    )


def load_benchmark_tasks(path: str | Path, max_cases: Optional[int] = None) -> List[BenchmarkTask]:
    """Load benchmark tasks from JSONL with schema validation."""

    tasks: List[BenchmarkTask] = []
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            raw = json.loads(text)
            task = _validate_task(raw, line_number)
            tasks.append(task)
            if max_cases is not None and len(tasks) >= max_cases:
                break

    return tasks
