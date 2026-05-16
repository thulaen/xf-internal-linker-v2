from __future__ import annotations

import hashlib
import json
import sys
import time


def dedupe_key(source: str, event_type: str, payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{event_type}:{digest}"


def main() -> int:
    iterations = int(sys.argv[1])
    payload = json.loads(sys.argv[2])
    start = time.perf_counter_ns()
    for _ in range(iterations):
        dedupe_key("wp", "post_updated", payload)
    elapsed = time.perf_counter_ns() - start
    print(elapsed / iterations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
