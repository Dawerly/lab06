import pytest

from closures import make_backoff, make_counter, make_logger


def test_counter_state_and_independence() -> None:
    a, b = make_counter(10), make_counter()
    assert [a(), a(), b(), a()] == [11, 12, 1, 13]


def test_fixed_and_exponential() -> None:
    fixed = make_backoff(delay=0.5)
    exponential = make_backoff(delay=0.5, factor=2)
    assert [fixed(i) for i in (1, 2, 3)] == [0.5, 0.5, 0.5]
    assert [exponential(i) for i in (1, 2, 3)] == [0.5, 1, 2]
    with pytest.raises(ValueError):
        fixed(0)


@pytest.mark.parametrize("delay,factor", [(-1, 1), (1, 0.5), (float("inf"), 1)])
def test_invalid_policy(delay: float, factor: float) -> None:
    with pytest.raises(ValueError):
        make_backoff(delay=delay, factor=factor)


def test_logger_closure() -> None:
    logs: list[str] = []
    make_logger("TASK", logs.append)("ready")
    assert logs == ["[TASK] ready"]
