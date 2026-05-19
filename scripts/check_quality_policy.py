#!/usr/bin/env python3
"""Enforce realistic changed-target quality gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ANGULAR_LINE_TARGET = 95.0
ANGULAR_BRANCH_TARGET = 85.0


def _git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _changed_files() -> list[str]:
    env_value = os.environ.get("QUALITY_CHANGED_FILES", "")
    if env_value:
        return [line.strip() for line in env_value.splitlines() if line.strip()]
    files: list[str] = []
    files.extend(_git_lines("diff", "--cached", "--name-only", "--diff-filter=ACM"))
    files.extend(_git_lines("diff", "--name-only", "--diff-filter=ACM", "HEAD"))
    files.extend(_git_lines("ls-files", "--others", "--exclude-standard"))
    return sorted(set(files))


def _new_files() -> set[str]:
    env_value = os.environ.get("QUALITY_NEW_FILES", "")
    if env_value:
        return {line.strip() for line in env_value.splitlines() if line.strip()}
    files = set(_git_lines("diff", "--cached", "--name-only", "--diff-filter=A"))
    files.update(_git_lines("diff", "--name-only", "--diff-filter=A", "HEAD"))
    files.update(_git_lines("ls-files", "--others", "--exclude-standard"))
    return files


def _angular_targets(files: list[str]) -> list[str]:
    return [
        path
        for path in files
        if path.startswith("frontend/src/app/")
        and (path.endswith(".component.ts") or path.endswith(".service.ts"))
        and not path.endswith(".spec.ts")
    ]


def _coverage_key(repo_path: str) -> str:
    # 2026-05-17 — the Angular tests now run from /repo/frontend (host-
    # mounted, not the stale image-built /app) so the coverage-summary.json
    # keys are /repo/frontend/src/... rather than /app/src/.... Return the
    # new form here. The legacy /app/... key is also returned as a fallback
    # via _metric() so old baseline files keep working during the migration.
    return "/repo/frontend/" + repo_path.removeprefix("frontend/")


def _legacy_coverage_key(repo_path: str) -> str:
    """Legacy key shape used when tests ran from the image-built /app."""
    return "/app/" + repo_path.removeprefix("frontend/")


def _load_baseline(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("frontend", {}).get("files", {})


def _baseline_metric(baseline: dict[str, Any], path: str, metric: str) -> float | None:
    value = baseline.get(path)
    if isinstance(value, dict):
        metric_value = value.get(metric)
        return float(metric_value) if metric_value is not None else None
    return None


def _metric(report: dict[str, Any], path: str, metric: str) -> float:
    # Try new key first (/repo/frontend/...), then fall back to legacy
    # (/app/...) for any old coverage report still using the image-built
    # working directory.
    for key_fn in (_coverage_key, _legacy_coverage_key):
        value = report.get(key_fn(path), {}).get(metric, {}).get("pct")
        if value is not None:
            return float(value)
    raise RuntimeError(f"Missing Angular coverage data for {path}")


def _source_hash(path: str) -> str:
    file_path = REPO_ROOT / path
    if not file_path.is_file():
        return ""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _write_evidence(
    evidence_out: Path | None,
    *,
    status: str,
    file_path: str,
    target: float,
    actual: float,
    summary: str,
    fingerprint: str,
) -> None:
    if evidence_out is None:
        return
    evidence_out.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "check_type": "coverage",
        "status": status,
        "tool_name": "angular-ratchet",
        "command": "npm run test:ci -- --code-coverage=true",
        "summary": summary,
        "source_hash": _source_hash(file_path),
        "file_path": file_path,
        "failure_fingerprint": fingerprint,
        "target_percent": target,
        "actual_percent": actual,
        "details": {"policy": "changed-file-ratchet"},
    }
    with evidence_out.open("a", encoding="utf-8") as output:
        output.write(json.dumps(row, sort_keys=True) + "\n")


def _check_existing_metric(
    *,
    baseline: dict[str, Any],
    path: str,
    metric_name: str,
    target: float,
    actual: float,
) -> tuple[bool, str]:
    floor = _baseline_metric(baseline, path, metric_name)
    if actual + 0.01 >= target:
        return True, f"{path} {metric_name} meets the full target."
    if floor is None:
        return False, (
            f"{path} {metric_name} is {actual:.1f}%, below {target:.1f}%, "
            "and has no ratchet baseline."
        )
    if actual + 0.01 < floor:
        return False, (
            f"{path} {metric_name} dropped from {floor:.1f}% to {actual:.1f}%."
        )
    if actual <= floor + 0.01:
        return False, (
            f"{path} {metric_name} is below target and did not improve above "
            f"the {floor:.1f}% baseline."
        )
    return True, (
        f"{path} {metric_name} improved from {floor:.1f}% to {actual:.1f}%."
    )


def angular_coverage(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    baseline = _load_baseline(args.baseline)
    new_files = _new_files()
    targets = _angular_targets(_changed_files())
    if not targets:
        _write_evidence(
            args.evidence_out,
            status="passed",
            file_path="",
            target=ANGULAR_LINE_TARGET,
            actual=100.0,
            summary="No changed Angular component or service needed ratchet coverage.",
            fingerprint="angular-ratchet:no-targets",
        )
        print("No changed Angular component or service needed ratchet coverage.")
        return 0

    failed = False
    for path in targets:
        checks = [
            ("lines", ANGULAR_LINE_TARGET, _metric(report, path, "lines")),
            ("branches", ANGULAR_BRANCH_TARGET, _metric(report, path, "branches")),
        ]
        for metric_name, target, actual in checks:
            if path in new_files:
                ok = actual + 0.01 >= target
                message = (
                    f"{path} {metric_name} is {actual:.1f}% for new Angular code; "
                    f"target is {target:.1f}%."
                )
            else:
                ok, message = _check_existing_metric(
                    baseline=baseline,
                    path=path,
                    metric_name=metric_name,
                    target=target,
                    actual=actual,
                )
            print(message)
            _write_evidence(
                args.evidence_out,
                status="passed" if ok else "failed",
                file_path=path,
                target=target,
                actual=actual,
                summary=message,
                fingerprint=f"angular-ratchet:{path}:{metric_name}:{'ok' if ok else 'failed'}",
            )
            failed = failed or not ok
    return 1 if failed else 0


def angular_targets(_args: argparse.Namespace) -> int:
    for path in _angular_targets(_changed_files()):
        print(path.removeprefix("frontend/"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    coverage_parser = subparsers.add_parser("angular-coverage")
    coverage_parser.add_argument("--report", required=True, type=Path)
    coverage_parser.add_argument("--baseline", default=REPO_ROOT / ".coverage-baseline.json", type=Path)
    coverage_parser.add_argument("--evidence-out", type=Path)
    coverage_parser.set_defaults(func=angular_coverage)
    targets_parser = subparsers.add_parser("angular-targets")
    targets_parser.set_defaults(func=angular_targets)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
