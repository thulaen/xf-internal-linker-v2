import json
import sys
import time


def state_rw(iterations: int) -> float:
    data = {}
    started = time.perf_counter_ns()
    for index in range(iterations):
        key = str(index)
        data[("site", key)] = json.dumps({"value": "value", "ttl": 60}, sort_keys=True)
        if ("site", key) not in data:
            raise RuntimeError("missing key")
    return (time.perf_counter_ns() - started) / iterations


def state_cleanup(iterations: int) -> float:
    data = {str(index): {"value": "value", "expires": 1} for index in range(iterations)}
    started = time.perf_counter_ns()
    for key in list(data.keys()):
        if data[key]["expires"] <= 2:
            del data[key]
    return (time.perf_counter_ns() - started) / iterations


mode = sys.argv[1]
count = int(sys.argv[2])
print(state_rw(count) if mode == "state_rw" else state_cleanup(count))
