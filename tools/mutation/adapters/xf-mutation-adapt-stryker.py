#!/usr/bin/env python3
"""Adapt Stryker JSON into the shared mutation schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.schema import mutation_summary  # noqa: E402


def adapt(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    totals = data.get("files", {}).get("all", {}).get("summary", data.get("summary", {}))
    return mutation_summary(
        "stryker",
        int(totals.get("killed", 0)),
        int(totals.get("survived", 0)),
        int(totals.get("runtimeErrors", 0)) + int(totals.get("timeout", 0)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(adapt(args.report_json), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
