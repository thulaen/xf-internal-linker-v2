"""Tests for the commit quota cutoff state helper."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / ".githooks" / "commit_quota_state.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("commit_quota_state", HELPER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_record_failure_writes_cutoff_for_quota(tmp_path) -> None:
    helper = _load_helper()
    path = tmp_path / "state.json"
    now = datetime(2026, 6, 18, 12, 34, 55, tzinfo=timezone.utc)

    helper.record_failure(
        hook="check-autoissue-quota",
        code=2,
        reason="quota short",
        path=path,
        now=now,
    )

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["event"] == "precommit_failed"
    assert state["hook"] == "check-autoissue-quota"
    assert state["exit_code"] == 2
    assert helper.read_cutoff_for_quota(path) == "2026-06-18 12:34"


def test_record_success_writes_cutoff_for_quota(tmp_path) -> None:
    helper = _load_helper()
    path = tmp_path / "state.json"
    now = datetime(2026, 6, 18, 13, 4, 0, tzinfo=timezone.utc)

    helper.record_success(commit="abcdef1", path=path, now=now)

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["event"] == "commit_succeeded"
    assert state["commit"] == "abcdef1"
    assert helper.read_cutoff_for_quota(path) == "2026-06-18 13:04"


def test_missing_state_returns_no_cutoff(tmp_path) -> None:
    helper = _load_helper()

    assert helper.read_cutoff_for_quota(tmp_path / "missing.json") is None


def test_malformed_state_fails_closed(tmp_path) -> None:
    helper = _load_helper()
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")

    try:
        helper.read_cutoff_for_quota(path)
    except helper.QuotaStateError as exc:
        assert "unreadable" in str(exc)
    else:
        raise AssertionError("malformed quota state should fail closed")
