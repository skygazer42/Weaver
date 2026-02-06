"""
Reliability helpers for search providers.

Provides retries with exponential backoff and a simple per-provider
circuit breaker to avoid hammering failing backends.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReliabilityPolicy:
    """Runtime policy for retries and circuit breaker behavior."""

    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: float = 60.0


@dataclass
class _ProviderReliabilityState:
    consecutive_failures: int = 0
    opened_at: Optional[float] = None


class ProviderReliabilityManager:
    """
    Wrap provider calls with retry and circuit-breaker safeguards.

    `call()` never raises provider errors; it returns `[]` on failure so callers
    can keep fallback behavior deterministic.
    """

    def __init__(self, policy: Optional[ReliabilityPolicy] = None):
        self.policy = policy or ReliabilityPolicy()
        self._states: Dict[str, _ProviderReliabilityState] = {}
        self._lock = threading.Lock()

    def _state(self, provider_name: str) -> _ProviderReliabilityState:
        with self._lock:
            if provider_name not in self._states:
                self._states[provider_name] = _ProviderReliabilityState()
            return self._states[provider_name]

    def _record_success(self, provider_name: str) -> None:
        state = self._state(provider_name)
        with self._lock:
            state.consecutive_failures = 0
            state.opened_at = None

    def _record_failure(self, provider_name: str) -> None:
        state = self._state(provider_name)
        with self._lock:
            state.consecutive_failures += 1
            threshold = max(1, int(self.policy.circuit_breaker_failures))
            if state.consecutive_failures >= threshold:
                state.opened_at = time.monotonic()

    def _reset_if_expired(self, provider_name: str) -> None:
        state = self._state(provider_name)
        with self._lock:
            if state.opened_at is None:
                return
            reset_after = max(0.0, float(self.policy.circuit_breaker_reset_seconds))
            if reset_after == 0.0 or (time.monotonic() - state.opened_at) >= reset_after:
                state.opened_at = None
                state.consecutive_failures = 0

    def is_open(self, provider_name: str) -> bool:
        """Return whether provider circuit is currently open."""
        self._reset_if_expired(provider_name)
        state = self._state(provider_name)
        with self._lock:
            return state.opened_at is not None

    def call(self, provider_name: str, fn: Callable[[], Any]) -> Any:
        """
        Execute provider call with retry/backoff and circuit breaker.

        Returns `[]` on failure/circuit-open to match search fallback flow.
        """
        if self.is_open(provider_name):
            logger.warning(f"[reliability] circuit open for provider={provider_name}, skip call")
            return []

        attempts = max(1, int(self.policy.max_retries) + 1)
        for attempt in range(attempts):
            try:
                result = fn()
                self._record_success(provider_name)
                return result
            except Exception as e:
                self._record_failure(provider_name)
                is_last_attempt = attempt >= (attempts - 1)

                if self.is_open(provider_name):
                    logger.warning(
                        f"[reliability] opened circuit for provider={provider_name}: {e}"
                    )
                    return []

                if is_last_attempt:
                    logger.warning(
                        f"[reliability] provider={provider_name} failed after "
                        f"{attempts} attempts: {e}"
                    )
                    return []

                base = max(0.0, float(self.policy.retry_backoff_seconds))
                delay = base * (2**attempt)
                if delay > 0:
                    time.sleep(delay)

        return []
