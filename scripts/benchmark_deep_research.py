"""Run a reproducible deep research benchmark and write a JSON report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.benchmarks.deep_research_bench_loader import load_benchmark_tasks

DEFAULT_BENCH_FILE = ROOT / "eval" / "benchmarks" / "sample_tasks.jsonl"
DEFAULT_GOLDEN_FILE = ROOT / "eval" / "golden_queries.json"

_TIME_MARKERS = (
    "latest",
    "recent",
    "today",
    "current",
    "update",
    "news",
    "最新",
    "近期",
    "今天",
    "动态",
    "新闻",
)


def _is_time_sensitive_query(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    if any(marker in text for marker in _TIME_MARKERS):
        return True
    return bool(re.search(r"\b20\d{2}\b", text))


def _case_quality_targets(
    query: str,
    constraints: Dict[str, Any],
    expected_fields: List[str],
    base_query_coverage_target: float,
    base_freshness_target: float,
) -> Dict[str, Any]:
    freshness_days = constraints.get("freshness_days")
    freshness_days = int(freshness_days) if isinstance(freshness_days, (int, float)) else None
    time_sensitive = _is_time_sensitive_query(query) or (
        freshness_days is not None and freshness_days <= 30
    )

    field_complexity = len(expected_fields or [])
    complexity_bonus = 0.1 if field_complexity >= 4 else 0.05 if field_complexity >= 2 else 0.0

    query_coverage_target = min(
        1.0,
        max(0.0, float(base_query_coverage_target) + complexity_bonus),
    )
    freshness_target = min(
        1.0,
        max(
            0.0,
            float(base_freshness_target) + (0.15 if time_sensitive else 0.0),
        ),
    )

    return {
        "time_sensitive": time_sensitive,
        "freshness_days_constraint": freshness_days,
        "query_coverage_target": round(query_coverage_target, 3),
        "freshness_ratio_target": round(freshness_target, 3),
    }


def _load_golden_entries(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return {}

    by_id: Dict[str, Dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or "").strip()
        if key:
            by_id[key] = item
    return by_id


def run_benchmark(
    max_cases: int,
    mode: str,
    output: Path,
    bench_file: Path,
    min_query_coverage: float,
    min_freshness_ratio: float,
) -> Dict[str, Any]:
    tasks = load_benchmark_tasks(bench_file, max_cases=max_cases)
    golden = _load_golden_entries(DEFAULT_GOLDEN_FILE)

    cases: List[Dict[str, Any]] = []
    coverage_targets: List[float] = []
    freshness_targets: List[float] = []
    time_sensitive_cases = 0

    for task in tasks:
        golden_entry = golden.get(task.task_id)
        quality_targets = _case_quality_targets(
            query=task.query,
            constraints=task.constraints if isinstance(task.constraints, dict) else {},
            expected_fields=task.expected_fields if isinstance(task.expected_fields, list) else [],
            base_query_coverage_target=min_query_coverage,
            base_freshness_target=min_freshness_ratio,
        )
        if quality_targets["time_sensitive"]:
            time_sensitive_cases += 1
        coverage_targets.append(float(quality_targets["query_coverage_target"]))
        freshness_targets.append(float(quality_targets["freshness_ratio_target"]))

        case = {
            "id": task.task_id,
            "query": task.query,
            "mode": mode,
            "constraints": task.constraints,
            "expected_fields": task.expected_fields,
            "golden_available": bool(golden_entry),
            "quality_targets": quality_targets,
            "status": "ready",
        }
        cases.append(case)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "max_cases": max_cases,
        "benchmark_file": str(bench_file),
        "cases": cases,
        "summary": {
            "total_cases": len(cases),
            "golden_covered": sum(1 for c in cases if c["golden_available"]),
            "time_sensitive_cases": time_sensitive_cases,
            "avg_query_coverage_target": round(
                sum(coverage_targets) / len(coverage_targets), 3
            )
            if coverage_targets
            else 0.0,
            "avg_freshness_ratio_target": round(
                sum(freshness_targets) / len(freshness_targets), 3
            )
            if freshness_targets
            else 0.0,
            "quality_gate_defaults": {
                "min_query_coverage": min_query_coverage,
                "min_freshness_ratio": min_freshness_ratio,
            },
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deep research benchmark smoke runner")
    parser.add_argument("--max-cases", type=int, default=5, help="Maximum cases to run")
    parser.add_argument("--mode", choices=["auto", "tree", "linear"], default="auto")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON report path")
    parser.add_argument(
        "--min-query-coverage",
        type=float,
        default=0.6,
        help="Base minimum query coverage target (0-1) for benchmark policy",
    )
    parser.add_argument(
        "--min-freshness-ratio",
        type=float,
        default=0.4,
        help="Base minimum freshness ratio target (0-1) for benchmark policy",
    )
    parser.add_argument(
        "--bench-file",
        type=Path,
        default=DEFAULT_BENCH_FILE,
        help="Benchmark JSONL file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    max_cases = max(1, int(args.max_cases))
    min_query_coverage = min(1.0, max(0.0, float(args.min_query_coverage)))
    min_freshness_ratio = min(1.0, max(0.0, float(args.min_freshness_ratio)))
    report = run_benchmark(
        max_cases=max_cases,
        mode=args.mode,
        output=args.output,
        bench_file=args.bench_file,
        min_query_coverage=min_query_coverage,
        min_freshness_ratio=min_freshness_ratio,
    )
    print(f"Benchmark report written: {args.output} ({report['summary']['total_cases']} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
