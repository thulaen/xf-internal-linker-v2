#!/usr/bin/env python3
"""Adapt Python coverage XML into the shared shard-report schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.cobertura import line_rate  # noqa: E402


def adapt(path: Path) -> dict[str, object]:
    """Return a compact coverage report."""
    return {"tool": "coverage.py", "coverage_pct": round(line_rate(path), 2)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_xml", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(adapt(args.coverage_xml), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
