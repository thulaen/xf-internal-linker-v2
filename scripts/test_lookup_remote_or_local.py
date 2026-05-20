#!/usr/bin/env python3
"""Tests for the HTTP-first audit lookup client."""

from __future__ import annotations

import io
from urllib.error import URLError

from lookup_remote_or_local import main


def test_remote_success_prints_compatible_resolved_search_lines() -> None:
    stdout = io.StringIO()

    def post_json(_url: str, _payload: dict, _timeout: float) -> dict:
        return {
            "paths": {
                "scripts/lookup_disk_index.py": {
                    "result_count": 1,
                    "result_ids": [42],
                    "matches": [{"autoissue_id": 42}],
                }
            }
        }

    exit_code = main(
        ["--area", "scripts/lookup_disk_index.py"],
        post_json=post_json,
        run_local=lambda _args: 99,
        stdout=stdout,
    )

    assert exit_code == 0
    assert (
        stdout.getvalue().strip()
        == "[RESOLVED SEARCH: scripts/lookup_disk_index.py: 1 prior fix(es)] #42"
    )


def test_remote_failure_runs_disk_fallback_with_original_args() -> None:
    calls: list[list[str]] = []

    def post_json(_url: str, _payload: dict, _timeout: float) -> dict:
        raise URLError("backend down")

    def run_local(args: list[str]) -> int:
        calls.append(args)
        return 0

    exit_code = main(
        ["--area", "backend/apps/audit/views.py", "--agent", "gemini"],
        post_json=post_json,
        run_local=run_local,
        stdout=io.StringIO(),
    )

    assert exit_code == 0
    assert calls == [["--area", "backend/apps/audit/views.py", "--agent", "gemini"]]


def test_remote_failure_strips_remote_only_args_before_fallback() -> None:
    calls: list[list[str]] = []

    def post_json(_url: str, _payload: dict, _timeout: float) -> dict:
        raise URLError("backend down")

    exit_code = main(
        [
            "--area",
            "backend/apps/audit/views.py",
            "--url",
            "http://localhost:9/missing",
            "--timeout",
            "0.01",
        ],
        post_json=post_json,
        run_local=lambda args: calls.append(args) or 0,
        stdout=io.StringIO(),
    )

    assert exit_code == 0
    assert calls == [["--area", "backend/apps/audit/views.py"]]
