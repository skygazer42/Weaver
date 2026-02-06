# Deep Research Rollout Guide

## Scope

This guide covers rollout of Deep Research VNext capabilities:
- multi-search orchestration
- freshness ranking
- domain-aware provider profiles
- citation gate and quality loop
- budget guards and session cache
- benchmark smoke/regression

## Rollout Stages

### Stage 1: Local Validation

1. Run backend checks:
   - `make lint`
   - `make test`
2. Run frontend checks:
   - `pnpm -C web lint`
   - `pnpm -C web build`
3. Run benchmark smoke:
   - `python scripts/benchmark_deep_research.py --max-cases 3 --mode auto --output /tmp/bench.json`

Exit criteria:
- checks pass
- benchmark report generated

### Stage 2: Pre-Prod

1. Start with conservative settings:
   - `DEEPSEARCH_MODE=linear`
   - `SEARCH_STRATEGY=fallback`
   - `CITATION_GATE_MIN_COVERAGE=0.5`
2. Observe:
   - citation gate revise rate
   - average deepsearch latency
   - cache hit rate trends
3. Increase confidence:
   - enable `DEEPSEARCH_MODE=auto`
   - keep fallback search strategy unless provider health is stable

Exit criteria:
- no sustained error-rate regression
- acceptable latency and revise-loop behavior

### Stage 3: Production

1. Enable desired defaults:
   - `DEEPSEARCH_MODE=auto`
   - `SEARCH_ENABLE_FRESHNESS_RANKING=true`
2. Keep rollback toggles prepared (below).
3. Schedule nightly benchmark workflow.

## Rollback Switches

- Deep mode rollback:
  - `DEEPSEARCH_MODE=linear`
  - `TREE_EXPLORATION_ENABLED=false`
- Search reliability rollback:
  - `SEARCH_STRATEGY=fallback`
- Citation gate rollback:
  - lower `CITATION_GATE_MIN_COVERAGE`
- Cache rollback:
  - reduce `SEARCH_CACHE_TTL_SECONDS`
  - reduce `SEARCH_CACHE_MAX_SIZE`

## Troubleshooting

### Symptom: repeated revise loop

- Check `citation_coverage` in eval dimensions.
- Verify report output includes explicit citations.
- Temporarily relax `CITATION_GATE_MIN_COVERAGE`.

### Symptom: deepsearch too slow

- Set `DEEPSEARCH_MAX_SECONDS` and `DEEPSEARCH_MAX_TOKENS`.
- Reduce `DEEPSEARCH_QUERY_NUM` and `DEEPSEARCH_RESULTS_PER_QUERY`.
- Disable tree default in early rollout.

### Symptom: stale or repetitive sources

- Enable freshness ranking.
- Reduce cache TTL.
- Verify provider profile mapping for the domain.

## Operational Checklist

- [ ] CI green (backend + frontend)
- [ ] benchmark smoke report generated
- [ ] rollback env vars documented in deployment config
- [ ] citation gate threshold reviewed by product/ops
- [ ] nightly benchmark workflow enabled
