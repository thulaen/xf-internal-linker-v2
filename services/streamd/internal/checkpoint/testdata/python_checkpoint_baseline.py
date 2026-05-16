import json
import sys
import time


def write(iterations: int) -> float:
    catalog = []
    started = time.perf_counter_ns()
    for index in range(iterations):
        catalog.append(json.dumps({"job": "job", "step": index, "bytes": 64}, sort_keys=True))
    return (time.perf_counter_ns() - started) / iterations


def restore(iterations: int) -> float:
    snapshot = {"steps": {"step": 1}}
    started = time.perf_counter_ns()
    for _ in range(iterations):
        if "step" not in snapshot["steps"]:
            raise RuntimeError("missing step")
    return (time.perf_counter_ns() - started) / iterations


mode = sys.argv[1]
count = int(sys.argv[2])
print({"write": write, "restore": restore}[mode](count))
