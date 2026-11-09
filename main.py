"""Демонстрація планувальника без реального очікування."""

from closures import make_backoff, make_counter, make_logger
from decorators import cached, retries, timed


def main() -> None:
    print("=== ПЛАНУВАЛЬНИК ПОВТОРІВ | ВАРІАНТ 14 ===")
    log = make_logger("TASK", print)
    for name, factor in [("Фіксована", 1.0), ("Експоненційна", 2.0)]:
        counter = make_counter()
        waits: list[float] = []
        ticks = iter([0.0, 0.012])

        @timed(name, logger=log, clock=lambda: next(ticks))
        @retries(
            attempts=4,
            delay_policy=make_backoff(delay=0.5, factor=factor),
            sleep=waits.append,
            logger=log,
        )
        def task() -> str:
            if counter() < 4:
                raise TimeoutError("Тимчасова помилка задачі")
            return "готово"

        print(name, "політика:", task())
        print("Заплановані затримки:", waits)

    calls = make_counter()
    now = 0.0

    @cached(ttl=1, time_fn=lambda: now)
    def result(task_id: int) -> str:
        return f"задача {task_id}, обчислення {calls()}"

    print("Перший виклик:", result(14))
    print("Кеш-хіт:", result(14))
    now = 1.0
    print("Межа TTL:", result(14))
    print("Інвалідація:", result.cache_invalidate(lambda args, kw: args == (14,)))
    print("Після інвалідації:", result(14))
    result.cache_clear()
    print("Після очищення:", result(14))


if __name__ == "__main__":
    main()
