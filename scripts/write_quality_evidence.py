#!/usr/bin/env python3
"""Append one compact quality evidence row to a JSON-lines file."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _optional_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def _raw_report_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _source_hash(value: str, file_path: str) -> str:
    if value:
        return value
    if not file_path:
        return ""
    path = Path(file_path)
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--check-type", required=True)
    parser.add_argument("--status", required=True, choices=["passed", "failed"])
    parser.add_argument("--tool-name", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--tool-version", default="")
    parser.add_argument("--source-hash", default="")
    parser.add_argument("--file-path", default="")
    parser.add_argument("--failure-fingerprint", default="")
    parser.add_argument("--target-percent", default="")
    parser.add_argument("--actual-percent", default="")
    parser.add_argument("--raw-report-file", type=Path)
    parser.add_argument("--detail", action="append", default=[])
    args = parser.parse_args()

    details = {}
    for item in args.detail:
        key, _, value = item.partition("=")
        if key:
            details[key] = value

    row = {
        "check_type": args.check_type,
        "status": args.status,
        "tool_name": args.tool_name,
        "tool_version": args.tool_version,
        "command": args.command,
        "summary": args.summary,
        "source_hash": _source_hash(args.source_hash, args.file_path),
        "file_path": args.file_path,
        "failure_fingerprint": args.failure_fingerprint,
        "target_percent": _optional_float(args.target_percent),
        "actual_percent": _optional_float(args.actual_percent),
        "details": details,
        "raw_report_text": _raw_report_text(args.raw_report_file),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a", encoding="utf-8") as output:
        output.write(json.dumps(row, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
