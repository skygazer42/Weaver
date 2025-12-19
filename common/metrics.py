from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class RunMetrics:
    """Lightweight run-level metrics for research flows."""

    run_id: str
    model: str
    route: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    duration_ms: float = 0.0
    event_count: int = 0
    nodes_started: Dict[str, int] = field(default_factory=dict)
    nodes_completed: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    cancelled: bool = False

    def mark_event(self, event_type: str, node_name: str | None = None) -> None:
        self.event_count += 1
        if not node_name:
            return
        bucket = self.nodes_started if "start" in event_type else self.nodes_completed
        bucket[node_name] = bucket.get(node_name, 0) + 1

    def add_error(self, message: str) -> None:
        if message:
            self.errors.append(message)

    def finish(self, cancelled: bool = False) -> None:
        self.ended_at = datetime.utcnow()
        self.cancelled = cancelled
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000

    def to_dict(self) -> Dict[str, object]:
        return {
            "run_id": self.run_id,
            "model": self.model,
            "route": self.route,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": round(self.duration_ms, 2),
            "event_count": self.event_count,
            "nodes_started": self.nodes_started,
            "nodes_completed": self.nodes_completed,
            "errors": self.errors,
            "cancelled": self.cancelled,
        }


class RunMetricsRegistry:
    """In-memory registry for run metrics (per thread/run id)."""

    def __init__(self):
        self._runs: Dict[str, RunMetrics] = {}

    def start(self, run_id: str, model: str, route: str = "") -> RunMetrics:
        metrics = RunMetrics(run_id=run_id, model=model, route=route)
        self._runs[run_id] = metrics
        return metrics

    def get(self, run_id: str) -> Optional[RunMetrics]:
        return self._runs.get(run_id)

    def all(self) -> List[Dict[str, object]]:
        return [m.to_dict() for m in self._runs.values()]

    def finish(self, run_id: str, cancelled: bool = False) -> Optional[RunMetrics]:
        metrics = self._runs.get(run_id)
        if metrics:
            metrics.finish(cancelled=cancelled)
        return metrics


metrics_registry = RunMetricsRegistry()
