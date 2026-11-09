"""Замикання для стану, політики затримок і логування."""

from collections.abc import Callable
from math import isfinite


def make_counter(start: int = 0) -> Callable[[], int]:
    value = start

    def increment() -> int:
        nonlocal value
        value += 1
        return value

    return increment


def make_backoff(*, delay: float, factor: float = 1.0) -> Callable[[int], float]:
    """Номер невдалої спроби починається з 1; factor=1 дає фіксовану паузу."""
    if not isfinite(delay) or delay < 0 or not isfinite(factor) or factor < 1:
        raise ValueError("delay >= 0 і factor >= 1 мають бути скінченними")

    def policy(failed_attempt: int) -> float:
        if failed_attempt < 1:
            raise ValueError("Номер спроби має починатися з 1")
        return delay * factor ** (failed_attempt - 1)

    return policy


def make_logger(prefix: str, sink: Callable[[str], None]) -> Callable[[str], None]:
    def log(message: str) -> None:
        sink(f"[{prefix}] {message}")

    return log
