#!/usr/bin/env python3
"""Run one quality command and save compact evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from write_quality_evidence import main as write_evidence_main


def _status_name(returncode: int) -> str:
    return "passed" if returncode == 0 else "failed"


def _summary(args: argparse.Namespace, returncode: int) -> str:
    if returncode == 0:
        return args.pass_summary
    return f"{args.fail_summary} Exit code was {returncode}."


def _write(args: argparse.Namespace, returncode: int, report: Path) -> None:
    original_argv = sys.argv
    try:
        sys.argv = [
            "write_quality_evidence.py",
            "--out",
            str(args.evidence_out),
            "--check-type",
            args.check_type,
            "--status",
            _status_name(returncode),
            "--tool-name",
            args.tool_name,
            "--tool-version",
            args.tool_version,
            "--command",
            args.command,
            "--summary",
            _summary(args, returncode),
            "--source-hash",
            args.source_hash,
            "--file-path",
            args.file_path,
            "--failure-fingerprint",
            args.failure_fingerprint or f"{args.tool_name}:{returncode}",
            "--target-percent",
            args.target_percent,
            "--actual-percent",
            args.actual_percent,
            "--raw-report-file",
            str(report),
        ]
        write_evidence_main()
    finally:
        sys.argv = original_argv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-out", required=True, type=Path)
    parser.add_argument("--check-type", required=True)
    parser.add_argument("--tool-name", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--pass-summary", required=True)
    parser.add_argument("--fail-summary", required=True)
    parser.add_argument("--tool-version", default="")
    parser.add_argument("--source-hash", default="")
    parser.add_argument("--file-path", default="")
    parser.add_argument("--failure-fingerprint", default="")
    parser.add_argument("--target-percent", default="")
    parser.add_argument("--actual-percent", default="")
    args = parser.parse_args()

    report = Path("/tmp") / f"quality-step-{args.tool_name}.log"
    result = subprocess.run(
        args.command,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    report.write_text(result.stdout or "", encoding="utf-8", errors="replace")
    if result.stdout:
        print(result.stdout, end="")
    _write(args, result.returncode, report)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
