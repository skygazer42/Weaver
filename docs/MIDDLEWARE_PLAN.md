# Middleware & telemetry (step15)
- Logging: structured JSON optional; thread-based log files already; add OpenTelemetry spans around nodes/tools.
- Metrics: RunMetrics registry added; expose /api/runs endpoints (done). Next: push to Prometheus.
- Tracing: plan to wrap research_graph.astream_events with span per node.
