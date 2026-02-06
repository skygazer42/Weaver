"""Run a reproducible deep research benchmark and write a JSON report."""

from __future__ import annotations

import argparse
import json
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


def run_benchmark(max_cases: int, mode: str, output: Path, bench_file: Path) -> Dict[str, Any]:
    tasks = load_benchmark_tasks(bench_file, max_cases=max_cases)
    golden = _load_golden_entries(DEFAULT_GOLDEN_FILE)

    cases: List[Dict[str, Any]] = []
    for task in tasks:
        golden_entry = golden.get(task.task_id)
        case = {
            "id": task.task_id,
            "query": task.query,
            "mode": mode,
            "constraints": task.constraints,
            "expected_fields": task.expected_fields,
            "golden_available": bool(golden_entry),
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
        "--bench-file",
        type=Path,
        default=DEFAULT_BENCH_FILE,
        help="Benchmark JSONL file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    max_cases = max(1, int(args.max_cases))
    report = run_benchmark(
        max_cases=max_cases,
        mode=args.mode,
        output=args.output,
        bench_file=args.bench_file,
    )
    print(f"Benchmark report written: {args.output} ({report['summary']['total_cases']} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
