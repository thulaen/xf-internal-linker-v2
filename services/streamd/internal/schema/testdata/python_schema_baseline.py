"""Python baseline for schema compatibility speed checks."""

import sys
import time


SCHEMA = {"id": ("string", True)}
PAYLOAD = {"id": "string"}


def parse_iterations(args: list[str]) -> int:
    if len(args) != 2:
        raise SystemExit("usage: python_schema_baseline.py <iterations>")
    iterations = int(args[1])
    if iterations <= 0:
        raise SystemExit("iterations must be greater than zero")
    return iterations


def check_schema_compatibility() -> None:
    for name, (kind, required) in SCHEMA.items():
        if required and PAYLOAD.get(name) != kind:
            raise RuntimeError("incompatible")


def measure_schema_compatibility(iterations: int) -> float:
    started = time.perf_counter_ns()
    for _ in range(iterations):
        check_schema_compatibility()
    return (time.perf_counter_ns() - started) / iterations


def main() -> None:
    iterations = parse_iterations(sys.argv)
    print(measure_schema_compatibility(iterations))


if __name__ == "__main__":
    main()
