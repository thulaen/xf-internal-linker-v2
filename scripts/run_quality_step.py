#!/usr/bin/env python3
"""Run one quality command and save compact evidence."""

from __future__ import annotations

import argparse
import os
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


def _artifact_dir() -> Path:
    return Path(os.environ.get("XF_TEST_ARTIFACT_DIR", "/tmp/xf-test-artifacts"))


def _is_test_like(check_type: str) -> bool:
    lowered = check_type.lower()
    return "test" in lowered or "mutation" in lowered or "fuzz" in lowered


def _failure_summary(report: Path, fallback: str) -> str:
    text = report.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return fallback
    return " ".join(text.split())[:600]


def _file_test_failure(args: argparse.Namespace, returncode: int, report: Path) -> None:
    if returncode == 0 or not _is_test_like(args.check_type):
        return
    if os.environ.get("XF_AUTOISSUE_ON_TEST_FAILURE", "1") == "0":
        return
    repo_root = Path(__file__).resolve().parents[1]
    manage_py = repo_root / "backend" / "manage.py"
    if not manage_py.exists():
        print("[quality-step] Test failed, but backend/manage.py was not found for AutoIssue filing.", file=sys.stderr)
        return
    command = [
        sys.executable,
        str(manage_py),
        "file_test_failure",
        "--tool",
        args.tool_name,
        "--test-target",
        args.file_path or args.command,
        "--test-file",
        args.file_path or "unknown",
        "--test-name",
        args.tool_name,
        "--failure-summary",
        _failure_summary(report, _summary(args, returncode)),
        "--severity",
        "high" if returncode == 124 else "medium",
        "--run-id",
        os.environ.get("XF_QUALITY_RUN_ID", "local-run"),
        "--shard-id",
        os.environ.get("XF_QUALITY_SHARD_ID", "local-shard"),
        "--worker",
        os.environ.get("XF_QUALITY_WORKER", "windows"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr or "[quality-step] Failed to file test-failure AutoIssue.", file=sys.stderr)


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
    parser.add_argument("--timeout-seconds", default=0, type=int)
    args = parser.parse_args()

    report_dir = _artifact_dir()
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"quality-step-{args.tool_name}.log"
    timeout = args.timeout_seconds or None
    try:
        result = subprocess.run(
            args.command,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = result.stdout or ""
        returncode = result.returncode
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        output = f"Timed out after {args.timeout_seconds} seconds.\n{partial}"
        returncode = 124
    report.write_text(output, encoding="utf-8", errors="replace")
    if output:
        print(output, end="")
    _write(args, returncode, report)
    _file_test_failure(args, returncode, report)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
