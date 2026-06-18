#!/usr/bin/env python3
"""Extract a small summary from a Bazel event stream JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize(path: Path) -> dict[str, int]:
    """Return event and failure counts from newline-delimited JSON."""
    events = 0
    failures = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events += 1
        event = json.loads(line)
        if "testResult" in event and event["testResult"].get("status") != "PASSED":
            failures += 1
    return {"events": events, "failures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bep_json", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(summarize(args.bep_json), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
