#!/usr/bin/env python3
"""Small report checker used by Docker quality scripts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise RuntimeError(f"Missing report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _angular_metric(data: Any, metric: str) -> float:
    total = data.get("total", {})
    value = total.get(metric, {}).get("pct")
    if value is None:
        raise RuntimeError(f"Missing Angular coverage metric: {metric}")
    return float(value)


def _mutation_score(data: Any, tool: str) -> float:
    if tool == "stryker" and isinstance(data, dict) and "mutationScore" in data:
        return float(data["mutationScore"])
    items = data if isinstance(data, list) else data.get("mutants", [])
    if not items:
        raise RuntimeError(f"Missing mutation data for {tool}")
    killed_statuses = {"killed", "Killed", "Timeout"}
    killed = sum(1 for item in items if item.get("status") in killed_statuses)
    return 100.0 * killed / len(items)


def _print_result(name: str, target: float, actual: float, command: str) -> None:
    print(f"{name}: target={target:.1f}% actual={actual:.1f}%")
    print(f"Re-run command: {command}")
    if actual + 0.01 < target:
        raise RuntimeError(f"{name} is below the required target.")


def _write_evidence(
    *,
    path: Path | None,
    status: str,
    args: argparse.Namespace,
    actual: float | None,
    error: str = "",
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    check_type = "coverage" if args.kind == "angular-coverage" else "mutation"
    tool_name = args.tool or "angular"
    subject = args.metric or args.tool or args.kind
    summary = (
        f"{tool_name} {subject} quality check {status}. "
        f"Target was {args.target:.1f} percent. "
        f"Actual was {actual:.1f} percent. " if actual is not None else ""
    )
    if error:
        summary += f"Failure: {error}. "
    summary += f"Re-run with: {args.rerun}"
    evidence = {
        "check_type": check_type,
        "status": "passed" if status == "passed" else "failed",
        "tool_name": tool_name,
        "command": args.rerun,
        "summary": summary,
        "source_hash": args.source_hash,
        "file_path": args.file_path,
        "failure_fingerprint": f"{args.kind}:{subject}:{error or 'ok'}",
        "target_percent": args.target,
        "actual_percent": actual,
        "details": {"report": str(args.report), "kind": args.kind, "subject": subject},
        "raw_report_text": _report_text(args.report),
    }
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(evidence, sort_keys=True) + "\n")


def _report_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["angular-coverage", "mutation"], required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--metric", choices=["lines", "branches", "statements", "functions"])
    parser.add_argument("--tool", choices=["mutmut", "stryker", "mull"])
    parser.add_argument("--target", required=True, type=float)
    parser.add_argument("--rerun", required=True)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--source-hash", default="")
    parser.add_argument("--file-path", default="")
    parser.add_argument("--debt-only", action="store_true")
    args = parser.parse_args()

    actual: float | None = None
    try:
        data = _load_json(args.report)
        if args.kind == "angular-coverage":
            if not args.metric:
                raise RuntimeError("--metric is required for Angular coverage")
            actual = _angular_metric(data, args.metric)
            name = f"Angular {args.metric} coverage"
        else:
            if not args.tool:
                raise RuntimeError("--tool is required for mutation reports")
            actual = _mutation_score(data, args.tool)
            name = f"{args.tool} mutation score"
        _print_result(name, args.target, actual, args.rerun)
        _write_evidence(path=args.evidence_out, status="passed", args=args, actual=actual)
        return 0
    except (json.JSONDecodeError, RuntimeError) as error:
        _write_evidence(
            path=args.evidence_out,
            status="failed",
            args=args,
            actual=actual,
            error=str(error),
        )
        print(f"FAIL: {error}", file=sys.stderr)
        print(f"Required target: {args.target:.1f}%", file=sys.stderr)
        print(f"Re-run command: {args.rerun}", file=sys.stderr)
        if args.debt_only:
            print("Recorded as quality debt; this does not block the normal commit gate.")
            return 0
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
