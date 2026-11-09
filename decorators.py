"""Параметризовані HOF з ін'єкцією часу, політики, sleep і logger."""

from collections.abc import Callable
from functools import wraps
from math import isfinite
from threading import Lock
from time import monotonic, perf_counter
from time import sleep as real_sleep
from typing import Literal, ParamSpec, Protocol, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")
Key = tuple[tuple[object, ...], tuple[tuple[str, object], ...]]
Predicate = Callable[[tuple[object, ...], dict[str, object]], bool]


def timed(
    label: str | None = None,
    *,
    unit: Literal["s", "ms", "us"] = "ms",
    logger: Callable[[str], None],
    clock: Callable[[], float] = perf_counter,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    factor = {"s": 1.0, "ms": 1000.0, "us": 1_000_000.0}[unit]

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = clock()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = (clock() - start) * factor
                logger(f"[timed] {label or func.__name__}: {elapsed:.3f} {unit}")

        return wrapper

    return decorate


def retries(
    *,
    attempts: int,
    delay_policy: Callable[[int], float],
    exceptions: tuple[type[Exception], ...] = (TimeoutError,),
    sleep: Callable[[float], None] = real_sleep,
    logger: Callable[[str], None],
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    if attempts < 1 or not exceptions:
        raise ValueError("attempts >= 1; exceptions має бути непорожнім")

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == attempts:
                        logger(f"[retries] вичерпано {attempt} спроб")
                        raise
                    wait = delay_policy(attempt)
                    if not isfinite(wait) or wait < 0:
                        raise ValueError("Політика має повертати скінченну паузу >= 0")
                    logger(f"[retries] спроба {attempt}, пауза {wait:.3f} s")
                    sleep(wait)
            raise AssertionError("Недосяжний код")

        return wrapper

    return decorate


class Cached(Protocol[P, R]):
    __name__: str
    __doc__: str | None
    __wrapped__: Callable[P, R]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def cache_clear(self) -> None: ...
    def cache_invalidate(self, predicate: Predicate) -> int: ...


def cached(
    *,
    ttl: float | None = None,
    time_fn: Callable[[], float] = monotonic,
) -> Callable[[Callable[P, R]], Cached[P, R]]:
    if ttl is not None and (not isfinite(ttl) or ttl < 0):
        raise ValueError("TTL має бути скінченним >= 0 або None")

    def decorate(func: Callable[P, R]) -> Cached[P, R]:
        cache: dict[Key, tuple[float | None, R]] = {}
        lock = Lock()

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key: Key = (args, tuple(sorted(kwargs.items())))
            hash(key)  # Явно відхиляємо нехешовані аргументи.
            with lock:
                entry = cache.get(key)
                if entry is not None:
                    expiry, value = entry
                    if expiry is None or time_fn() < expiry:
                        return value
                    del cache[key]
            value = func(*args, **kwargs)
            expiry = None if ttl is None else time_fn() + ttl
            with lock:
                cache[key] = (expiry, value)
            return value

        def clear() -> None:
            with lock:
                cache.clear()

        def invalidate(predicate: Predicate) -> int:
            with lock:
                keys = [key for key in cache if predicate(key[0], dict(key[1]))]
                for key in keys:
                    del cache[key]
                return len(keys)

        setattr(wrapper, "cache_clear", clear)
        setattr(wrapper, "cache_invalidate", invalidate)
        return cast(Cached[P, R], wrapper)

    return decorate
