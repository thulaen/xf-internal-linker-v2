#!/usr/bin/env python3
"""Adapt JavaScript coverage summary JSON into the shared shard-report schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def adapt(path: Path) -> dict[str, object]:
    """Return a compact JavaScript coverage report."""
    data = json.loads(path.read_text(encoding="utf-8"))
    total = data.get("total", {})
    pct = float(total.get("lines", {}).get("pct", 0))
    return {"tool": "karma-coverage", "coverage_pct": round(pct, 2)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(adapt(args.summary_json), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
