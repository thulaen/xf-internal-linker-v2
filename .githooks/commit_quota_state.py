#!/usr/bin/env python3
"""Record the commit-attempt cutoff used by quota checks."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "audit" / "commit_quota_state.json"
_STATE_VERSION = 1
_QUOTA_TIME_FORMAT = "%Y-%m-%d %H:%M"


class QuotaStateError(RuntimeError):
    """Raised when quota state exists but cannot be trusted."""


def read_cutoff_for_quota(path: Path = STATE_FILE) -> str | None:
    """Return the cutoff timestamp in the verifier's accepted format."""
    if not path.exists():
        return None
    state = _read_state(path)
    cutoff = state.get("cutoff_at")
    if not isinstance(cutoff, str):
        raise QuotaStateError("commit quota state is missing cutoff_at")
    return _parse_cutoff(cutoff).strftime(_QUOTA_TIME_FORMAT)


def record_failure(
    *,
    hook: str,
    code: int,
    reason: str,
    path: Path = STATE_FILE,
    now: datetime | None = None,
) -> None:
    """Store a new quota cutoff for a failed commit attempt."""
    stamp = _format_timestamp(now or datetime.now(timezone.utc))
    _write_state(
        path,
        {
            "version": _STATE_VERSION,
            "event": "precommit_failed",
            "cutoff_at": stamp,
            "hook": hook,
            "exit_code": code,
            "reason": reason,
        },
    )


def record_success(
    *,
    commit: str,
    path: Path = STATE_FILE,
    now: datetime | None = None,
) -> None:
    """Store a new quota cutoff for a successful commit."""
    stamp = _format_timestamp(now or datetime.now(timezone.utc))
    _write_state(
        path,
        {
            "version": _STATE_VERSION,
            "event": "commit_succeeded",
            "cutoff_at": stamp,
            "commit": commit,
        },
    )


def main(argv: list[str] | None = None) -> int:
    """Run the quota state command-line helper."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except QuotaStateError as exc:
        print(f"FAIL quota state: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.command == "record-failure":
        record_failure(hook=args.hook, code=args.code, reason=args.reason)
        return 0
    if args.command == "record-success":
        record_success(commit=args.commit)
        return 0
    cutoff = read_cutoff_for_quota()
    if cutoff is None:
        return 1
    print(cutoff)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    failure = subparsers.add_parser("record-failure")
    failure.add_argument("--hook", required=True)
    failure.add_argument("--code", required=True, type=int)
    failure.add_argument("--reason", default="pre-commit exited non-zero")

    success = subparsers.add_parser("record-success")
    success.add_argument("--commit", required=True)

    subparsers.add_parser("cutoff")
    return parser


def _read_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QuotaStateError("commit quota state is unreadable") from exc
    if not isinstance(state, dict):
        raise QuotaStateError("commit quota state is not a JSON object")
    if state.get("version") != _STATE_VERSION:
        raise QuotaStateError("commit quota state version is unsupported")
    return state


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(state, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
    temp_path.replace(path)


def _parse_cutoff(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise QuotaStateError("commit quota cutoff_at is malformed") from exc


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    sys.exit(main())
