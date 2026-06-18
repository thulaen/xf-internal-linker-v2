"""Tests for the session-start gate script (Python-only path).

The script calls Django's /api/session-gate/ directly — the Go
"startupd" middleman is retired (ADR 0007). The behavioral tests cover
the pure helpers so they run without HTTP or Docker; the documentation
tests at the bottom pin the agent-rule files to the cached-payload
startup protocol.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from scripts import session_start_payload


ROOT = Path(__file__).resolve().parents[1]


def test_gate_path_is_the_django_endpoint() -> None:
    assert session_start_payload.GATE_PATH == "/api/session-gate/"
    assert session_start_payload.DEFAULT_BASE_URL == "http://192.168.0.91:30080"


def test_stdout_reconfigure_helper_is_safe() -> None:
    session_start_payload._prefer_utf8_stdout()


def test_build_marker_block_orders_markers_canonically() -> None:
    markers = {
        "tdd_preflight": "[TDD PREFLIGHT: ...]",
        "lessons": "[LESSONS BEFORE START: ...]",
        "registry": "[REGISTRY READ: ...]",
        "sticky": "[STICKY 1 READ: ...]",
        "snapshots": "[SNAPSHOTS READ: skipped — snapshotd unavailable]",
        "paper_trail": "[PAPER TRAIL READ: ...]",
    }

    block = session_start_payload.build_marker_block(markers)

    assert block.splitlines() == [
        "[STICKY 1 READ: ...]",
        "[REGISTRY READ: ...]",
        "[PAPER TRAIL READ: ...]",
        "[SNAPSHOTS READ: skipped — snapshotd unavailable]",
        "[LESSONS BEFORE START: ...]",
        "[TDD PREFLIGHT: ...]",
    ]


def test_build_marker_block_appends_unknown_markers() -> None:
    markers = {"sticky": "[STICKY 1 READ: ...]", "future": "[FUTURE: x]"}

    block = session_start_payload.build_marker_block(markers)

    assert block.splitlines() == ["[STICKY 1 READ: ...]", "[FUTURE: x]"]


def test_build_marker_block_skips_empty_markers() -> None:
    markers = {"sticky": "", "registry": "[REGISTRY READ: ...]"}

    assert session_start_payload.build_marker_block(markers) == "[REGISTRY READ: ...]"


def test_gate_state_carries_session_type_for_the_quota_hook() -> None:
    # .githooks/check-autoissue-quota.py reads session_type from
    # audit/session_gate_state.json — it must always be present.
    state = session_start_payload.build_gate_state(
        "reconciliation", {"total_open_count": 7}
    )

    assert state == {"session_type": "reconciliation", "total_open_count": 7}


def test_gate_state_defaults_missing_total_to_zero() -> None:
    state = session_start_payload.build_gate_state("feature", {})

    assert state == {"session_type": "feature", "total_open_count": 0}


@mock.patch("scripts.session_start_payload.urlopen")
def test_call_gate_builds_url_with_type_and_areas(mocked_urlopen) -> None:
    mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
        {"markers": {"sticky": "[STICKY 1 READ: ...]"}, "total_open_count": 3}
    ).encode("utf-8")

    data = session_start_payload._call_gate(
            "http://192.168.0.91:30080",
        "reconciliation",
        ["backend/apps/auto_issues", "backend/apps/api"],
        timeout=1.0,
    )

    called_url = mocked_urlopen.call_args[0][0]
    assert called_url.startswith("http://192.168.0.91:30080/api/session-gate/?")
    assert "type=reconciliation" in called_url
    assert called_url.count("area=") == 2
    assert data["total_open_count"] == 3


@mock.patch("scripts.session_start_payload.urlopen")
def test_call_gate_exits_with_plain_english_fix_when_backend_down(
    mocked_urlopen, capsys
) -> None:
    from urllib.error import URLError

    mocked_urlopen.side_effect = URLError("connection refused")

    try:
        session_start_payload._call_gate(
            "http://localhost", "feature", [], timeout=1.0
        )
    except SystemExit as exc:
        message = str(exc.code)
    else:  # pragma: no cover - the call must exit
        raise AssertionError("expected SystemExit")

    assert "FAIL: the backend is not responding" in message
    assert "kubectl -n xf-app get pods -l app=backend" in message
    assert "docker compose" not in message


# ── Documentation pins (unchanged protocol surface) ──────────────────


def test_agent_rule_files_make_cached_payload_the_default() -> None:
    for relative_path in ("AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md", "AI-CONTEXT.md"):
        text = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "python scripts/session_start_payload.py" in text
        assert "refresh_session_start_payload" in text
        assert "Do not run `docker compose exec -T backend python manage.py refresh_session_start_payload` during normal chat startup" in text or "Normal chat startup must not run `docker compose exec -T backend python manage.py refresh_session_start_payload`" in text
        assert "Do not read `audit/session_start_payload.jsonl`" in text or "read `audit/session_start_payload.jsonl`" in text
        assert "only run live startup commands when the user explicitly asks" in text.lower()


def test_startup_banner_uses_fast_payload_without_legacy_live_fallback() -> None:
    text = (ROOT / "scripts" / "session-start-banner.ps1").read_text(encoding="utf-8")

    assert "scripts/session_start_payload.py" in text
    assert "print_open_issues" not in text
    assert "print_resolved_issues" not in text
    assert "REPORT-REGISTRY.md" not in text
    assert "refresh_session_start_payload" not in text
