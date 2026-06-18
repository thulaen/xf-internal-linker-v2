#!/usr/bin/env python3
"""Adapt Rust coverage summary JSON into the shared shard-report schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def adapt(path: Path) -> dict[str, object]:
    """Return a compact Rust coverage report."""
    data = json.loads(path.read_text(encoding="utf-8"))
    pct = float(data.get("data", [{}])[0].get("totals", {}).get("lines", {}).get("percent", 0))
    return {"tool": "cargo-llvm-cov", "coverage_pct": round(pct, 2)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(adapt(args.summary_json), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
