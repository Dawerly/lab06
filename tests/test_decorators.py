import inspect

import pytest

from closures import make_backoff
from decorators import cached, retries, timed


def test_timed_success_and_metadata() -> None:
    logs: list[str] = []
    ticks = iter([0.0, 0.012345])

    def work(x: int, *, extra: int = 1) -> int:
        """Обчислення."""
        return x + extra

    wrapped = timed("work", logger=logs.append, clock=lambda: next(ticks))(work)
    assert wrapped(4, extra=2) == 6
    assert logs == ["[timed] work: 12.345 ms"]
    assert wrapped.__name__ == work.__name__ and wrapped.__doc__ == work.__doc__
    assert inspect.unwrap(wrapped) is work


def test_composition_counts_each_attempt() -> None:
    logs: list[str] = []
    waits: list[float] = []
    calls = 0

    def work() -> int:
        """Нестабільна задача."""
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("retry")
        return 14

    ticks = iter([0.0, 0.001, 1.0, 1.001, 2.0, 2.001])
    measured = timed(logger=logs.append, clock=lambda: next(ticks))(work)
    wrapped = retries(
        attempts=3,
        delay_policy=make_backoff(delay=1, factor=2),
        sleep=waits.append,
        logger=logs.append,
    )(measured)
    assert wrapped() == 14 and calls == 3 and waits == [1, 2]
    assert sum("[timed]" in line for line in logs) == 3
    assert wrapped.__name__ == work.__name__ and wrapped.__doc__ == work.__doc__
    assert inspect.unwrap(wrapped) is work


def test_timed_outside_retries_measures_whole_task() -> None:
    calls = 0
    logs: list[str] = []

    def task() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError()
        return "ok"

    retry = retries(
        attempts=2, delay_policy=lambda i: 0, sleep=lambda d: None, logger=logs.append
    )(task)
    ticks = iter([0.0, 1.0])
    wrapped = timed(logger=logs.append, clock=lambda: next(ticks))(retry)
    assert wrapped() == "ok"
    assert sum("[timed]" in line for line in logs) == 1


def test_exhaustion_and_unmatched_exception() -> None:
    waits: list[float] = []
    original = TimeoutError("original")

    def fail() -> None:
        raise original

    wrapped = retries(
        attempts=2, delay_policy=lambda i: 0, sleep=waits.append, logger=lambda s: None
    )(fail)
    with pytest.raises(TimeoutError) as caught:
        wrapped()
    assert caught.value is original and waits == [0]
    unmatched = retries(
        attempts=3,
        exceptions=(ValueError,),
        delay_policy=lambda i: 0,
        sleep=waits.append,
        logger=lambda s: None,
    )(fail)
    with pytest.raises(TimeoutError):
        unmatched()
    assert waits == [0]


def test_one_attempt_and_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        retries(attempts=0, delay_policy=lambda i: 0, logger=lambda s: None)
    waits: list[float] = []

    def fail() -> None:
        raise TimeoutError()

    wrapped = retries(
        attempts=1, delay_policy=lambda i: 0, sleep=waits.append, logger=lambda s: None
    )(fail)
    with pytest.raises(TimeoutError):
        wrapped()
    assert waits == []
    invalid = retries(
        attempts=2, delay_policy=lambda i: -1, sleep=waits.append, logger=lambda s: None
    )(fail)
    with pytest.raises(ValueError):
        invalid()
    assert waits == []


def test_cache_ttl_invalidation_and_metadata() -> None:
    now, calls = 0.0, 0

    def compute(x: int, *, extra: int = 0) -> int:
        """Результат задачі."""
        nonlocal calls
        calls += 1
        return x + extra

    wrapped = cached(ttl=1, time_fn=lambda: now)(compute)
    assert wrapped(2, extra=3) == wrapped(2, extra=3) == 5
    assert calls == 1
    now = 1.0
    assert wrapped(2, extra=3) == 5 and calls == 2
    wrapped(9)
    assert wrapped.cache_invalidate(lambda a, kw: a == (2,) and kw == {"extra": 3}) == 1
    assert wrapped.cache_invalidate(lambda a, kw: a == (2,)) == 0
    wrapped(9)
    assert calls == 3
    wrapped.cache_clear()
    wrapped(9)
    assert calls == 4
    assert wrapped.__name__ == compute.__name__ and wrapped.__doc__ == compute.__doc__
    assert wrapped.__wrapped__ is compute


@pytest.mark.parametrize("ttl", [-1, float("nan"), float("inf")])
def test_invalid_ttl(ttl: float) -> None:
    with pytest.raises(ValueError):
        cached(ttl=ttl)


def test_zero_ttl_and_exceptions_not_cached() -> None:
    calls = 0

    @cached(ttl=0, time_fn=lambda: 0.0)
    def work() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert work() == 1 and work() == 2

    @cached()
    def fail() -> None:
        raise ValueError("not stored")

    for _ in range(2):
        with pytest.raises(ValueError):
            fail()
