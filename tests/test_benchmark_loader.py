import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.benchmarks.deep_research_bench_loader import BenchmarkTask, load_benchmark_tasks


def test_benchmark_loader_parses_sample_tasks():
    sample_file = ROOT / "eval" / "benchmarks" / "sample_tasks.jsonl"

    tasks = load_benchmark_tasks(sample_file)

    assert tasks
    assert isinstance(tasks[0], BenchmarkTask)
    assert tasks[0].query
    assert tasks[0].expected_fields


def test_benchmark_loader_respects_max_cases():
    sample_file = ROOT / "eval" / "benchmarks" / "sample_tasks.jsonl"

    tasks = load_benchmark_tasks(sample_file, max_cases=2)

    assert len(tasks) == 2
