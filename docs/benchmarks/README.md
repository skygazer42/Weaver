# Deep Research Benchmarks

## Files

- `eval/benchmarks/sample_tasks.jsonl`: sample benchmark inputs
- `eval/golden_queries.json`: lightweight golden baseline cases
- `scripts/benchmark_deep_research.py`: regression smoke runner

## Run Smoke Benchmark

```bash
python scripts/benchmark_deep_research.py \
  --max-cases 3 \
  --mode auto \
  --output /tmp/bench.json
```

## CLI Options

- `--max-cases`: number of benchmark cases to include
- `--mode`: `auto|tree|linear`
- `--output`: output JSON report path
- `--bench-file`: custom JSONL benchmark file path

## JSONL Schema

Each line must be one JSON object:

```json
{
  "id": "case_001",
  "query": "Latest AI chip market share in 2025",
  "constraints": {"freshness_days": 30},
  "expected_fields": ["market_share", "top_vendors"],
  "metadata": {"domain": "financial"}
}
```

Required fields:
- `query` (string)
- `constraints` (object)
- `expected_fields` (non-empty string array)

## Report Output

The runner writes a JSON report containing:
- run metadata (`mode`, `max_cases`, timestamp)
- selected cases
- golden coverage summary

Use this as a reproducible smoke signal in CI/nightly workflows.
