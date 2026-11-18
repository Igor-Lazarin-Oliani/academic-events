"""Budget, retry com backoff e circuit breaker: a infraestrutura em volta do modelo é determinística."""

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from app.agentic.ports.model import ModelError, ModelUnavailable

T = TypeVar("T")


class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Budget:
    max_steps: int = 8
    max_tokens: int = 60_000
    timeout_seconds: float = 120.0
    steps: int = 0
    tokens: int = 0
    started: float = field(default_factory=time.monotonic)

    def check(self) -> None:
        if self.steps >= self.max_steps:
            raise BudgetExceeded(f"max_steps ({self.max_steps})")
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"max_tokens ({self.max_tokens})")
        if self.elapsed() >= self.timeout_seconds:
            raise BudgetExceeded(f"timeout ({self.timeout_seconds:.0f}s)")

    def consume(self, tokens: int) -> None:
        self.steps += 1
        self.tokens += tokens

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def snapshot(self) -> dict:
        return {"steps": self.steps, "max_steps": self.max_steps, "tokens": self.tokens, "max_tokens": self.max_tokens, "elapsed_s": round(self.elapsed(), 2)}


def with_retry(fn: Callable[[], T], *, retries: int = 2, base_delay: float = 1.0, on_retry: Callable[[int, Exception], None] | None = None, sleep=time.sleep) -> T:
    """Repete só falhas recuperáveis, com backoff exponencial e jitter."""
    attempt = 0
    while True:
        try:
            return fn()
        except ModelError as exc:
            if not exc.retryable or attempt >= retries:
                raise
            attempt += 1
            if on_retry:
                on_retry(attempt, exc)
            sleep(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.3))


class CircuitBreaker:
    """Depois de N falhas seguidas, abre por reset_seconds e falha rápido (sem esperar o timeout)."""

    def __init__(self, name: str, failure_threshold: int = 3, reset_seconds: float = 60.0, clock=time.monotonic):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            if self._clock() - self._opened_at >= self.reset_seconds:
                return "half_open"
            return "open"

    def call(self, fn: Callable[[], T]) -> T:
        if self.state == "open":
            raise ModelUnavailable(f"circuit '{self.name}' is open", retryable=False)
        try:
            result = fn()
        except ModelError:
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold or self._opened_at is not None:
                    self._opened_at = self._clock()
            raise
        with self._lock:
            self._failures = 0
            self._opened_at = None
        return result

    def reset(self) -> None:
        with self._lock:
            self._failures, self._opened_at = 0, None
