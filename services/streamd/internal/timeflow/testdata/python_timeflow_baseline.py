"""Python baselines for timeflow speed checks."""

import heapq
import sys
import time
from collections.abc import Callable


MODES = ("timer", "window", "watermark")


def measure_loop(iterations: int, operation: Callable[[int], None]) -> float:
    started = time.perf_counter_ns()
    for index in range(iterations):
        operation(index)
    return (time.perf_counter_ns() - started) / iterations


def measure_timer_schedule(iterations: int) -> float:
    heap = []

    def schedule(index: int) -> None:
        heapq.heappush(heap, (index, "site", b""))

    return measure_loop(iterations, schedule)


def measure_window_assignment(iterations: int) -> float:
    size = 60

    def assign(index: int) -> None:
        start = (index // size) * size
        _ = (start, start + size)

    return measure_loop(iterations, assign)


def measure_watermark_update(iterations: int) -> float:
    seen = {}

    def update(index: int) -> None:
        current = seen.get("site", -1)
        if index > current:
            seen["site"] = index - 1

    return measure_loop(iterations, update)


def parse_args(args: list[str]) -> tuple[str, int]:
    if len(args) != 3:
        raise SystemExit("usage: python_timeflow_baseline.py <mode> <iterations>")
    mode = args[1]
    if mode not in MODES:
        raise SystemExit(f"mode must be one of: {', '.join(MODES)}")
    iterations = int(args[2])
    if iterations <= 0:
        raise SystemExit("iterations must be greater than zero")
    return mode, iterations


def main() -> None:
    mode, iterations = parse_args(sys.argv)
    benchmarks = {
        "timer": measure_timer_schedule,
        "window": measure_window_assignment,
        "watermark": measure_watermark_update,
    }
    print(benchmarks[mode](iterations))


if __name__ == "__main__":
    main()
