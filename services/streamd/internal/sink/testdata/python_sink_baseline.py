import json
import sys
import time


def commit(iterations: int) -> float:
    committed = set()
    started = time.perf_counter_ns()
    for index in range(iterations):
        payload = json.dumps({"id": index, "rows": ["row"]}, sort_keys=True)
        committed.add(payload)
    return (time.perf_counter_ns() - started) / iterations


def twophase(iterations: int) -> float:
    states = {}
    started = time.perf_counter_ns()
    for index in range(iterations):
        key = str(index)
        states[key] = "prepared"
        states[key] = "committed"
    return (time.perf_counter_ns() - started) / iterations


mode = sys.argv[1]
count = int(sys.argv[2])
print({"commit": commit, "twophase": twophase}[mode](count))
