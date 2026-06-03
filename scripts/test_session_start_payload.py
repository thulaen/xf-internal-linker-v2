"""Tests for the non-Django startup payload wrapper."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from scripts import session_start_payload


ROOT = Path(__file__).resolve().parents[1]


def test_default_url_uses_loopback() -> None:
    assert session_start_payload.DEFAULT_URL == "http://127.0.0.1:8765/payload"


def test_stdout_reconfigure_helper_is_safe() -> None:
    session_start_payload._prefer_utf8_stdout()


def test_render_payload_can_print_autoissues_section() -> None:
    payload = {
        "body": "full",
        "autoissues": ["[REGISTRY READ: 1 open]", "#1 issue"],
    }

    rendered = session_start_payload._render_payload(
        payload,
        section="autoissues",
        raw_json=False,
    )

    assert rendered == "[REGISTRY READ: 1 open]\n#1 issue"


def test_render_payload_can_print_json() -> None:
    payload = {"body": "full", "autoissues": ["#1 issue"]}

    rendered = session_start_payload._render_payload(
        payload,
        section=None,
        raw_json=True,
    )

    assert '"autoissues": ["#1 issue"]' in rendered


def test_render_payload_inserts_stale_marker_after_handoff() -> None:
    payload = {
        "generated_at": "2026-05-26T00:00:00Z",
        "expires_at": "2026-05-26T00:01:00Z",
        "body": "[HANDOFF READ: old]\n[REGISTRY READ: old]",
    }

    rendered = session_start_payload._render_payload(
        payload,
        section=None,
        raw_json=False,
        stale=True,
        refresh_status="started",
    )

    lines = rendered.splitlines()
    assert lines[0] == "[HANDOFF READ: old]"
    assert lines[1].startswith("[STARTUP PAYLOAD STALE:")
    assert "refresh=started" in lines[1]
    assert lines[2] == "[REGISTRY READ: old]"


@mock.patch("scripts.session_start_payload.urlopen")
def test_read_payload_returns_current_body(mocked_urlopen) -> None:
    mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
        {
            "version": 1,
            "generated_at": "2026-05-26T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "markers": ["[REGISTRY READ: 0 open]"],
            "body": "[REGISTRY READ: 0 open]",
        }
    ).encode("utf-8")

    payload = session_start_payload.read_payload(
        session_start_payload.DEFAULT_URL,
        timeout_seconds=0.1,
    )

    assert payload["body"] == "[REGISTRY READ: 0 open]"


@mock.patch("scripts.session_start_payload.urlopen")
def test_read_payload_rejects_stale_body(mocked_urlopen) -> None:
    mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
        {
            "version": 1,
            "generated_at": "2026-05-26T00:00:00Z",
            "expires_at": "2026-05-26T00:01:00Z",
            "markers": [],
            "body": "old",
        }
    ).encode("utf-8")

    with pytest.raises(RuntimeError, match="stale"):
        session_start_payload.read_payload(
            session_start_payload.DEFAULT_URL,
            timeout_seconds=0.1,
        )


@mock.patch("scripts.session_start_payload._trigger_refresh")
@mock.patch("scripts.session_start_payload.urlopen")
def test_main_prints_stale_payload_instead_of_forcing_live_refresh(
    mocked_urlopen,
    mocked_refresh,
    capsys,
) -> None:
    mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
        {
            "version": 1,
            "generated_at": "2026-05-26T00:00:00Z",
            "expires_at": "2026-05-26T00:01:00Z",
            "markers": ["[HANDOFF READ: old]"],
            "body": "[HANDOFF READ: old]\n[REGISTRY READ: old]",
        }
    ).encode("utf-8")
    mocked_refresh.return_value = True

    with mock.patch("sys.argv", ["session_start_payload.py"]):
        result = session_start_payload.main()

    assert result == 0
    mocked_refresh.assert_called_once()
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines[0] == "[HANDOFF READ: old]"
    assert lines[1].startswith("[STARTUP PAYLOAD STALE:")
    assert "refresh=started" in lines[1]
    assert lines[2] == "[REGISTRY READ: old]"
    assert "cached startup payload is stale" not in captured.err


@mock.patch("scripts.session_start_payload._trigger_refresh")
@mock.patch("scripts.session_start_payload.urlopen")
def test_main_marks_stale_payload_when_refresh_start_fails(
    mocked_urlopen,
    mocked_refresh,
    capsys,
) -> None:
    mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
        {
            "version": 1,
            "generated_at": "2026-05-26T00:00:00Z",
            "expires_at": "2026-05-26T00:01:00Z",
            "markers": ["[HANDOFF READ: old]"],
            "body": "[HANDOFF READ: old]",
        }
    ).encode("utf-8")
    mocked_refresh.return_value = False

    with mock.patch("sys.argv", ["session_start_payload.py"]):
        result = session_start_payload.main()

    assert result == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "[HANDOFF READ: old]"
    assert "refresh=failed" in lines[1]


@mock.patch("scripts.session_start_payload._trigger_refresh")
@mock.patch("scripts.session_start_payload.urlopen")
def test_main_no_auto_refresh_rejects_stale_payload(
    mocked_urlopen,
    mocked_refresh,
    capsys,
) -> None:
    mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
        {
            "version": 1,
            "generated_at": "2026-05-26T00:00:00Z",
            "expires_at": "2026-05-26T00:01:00Z",
            "markers": ["[HANDOFF READ: old]"],
            "body": "[HANDOFF READ: old]",
        }
    ).encode("utf-8")

    with mock.patch("sys.argv", ["session_start_payload.py", "--no-auto-refresh"]):
        result = session_start_payload.main()

    assert result == 1
    mocked_refresh.assert_not_called()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cached startup payload is stale" in captured.err


def test_payload_expires_soon_detects_near_expiry() -> None:
    payload = {"expires_at": "2026-05-26T00:01:00Z"}

    with mock.patch("scripts.session_start_payload.datetime") as mocked_datetime:
        mocked_datetime.now.return_value = datetime(
            2026,
            5,
            26,
            0,
            0,
            30,
            tzinfo=timezone.utc,
        )
        mocked_datetime.fromisoformat = datetime.fromisoformat

        assert session_start_payload._payload_expires_soon(payload, 60.0)


@mock.patch("scripts.session_start_payload.subprocess.Popen")
def test_trigger_refresh_runs_refresh_in_background(mocked_popen) -> None:
    assert session_start_payload._trigger_refresh()

    mocked_popen.assert_called_once()
    args, kwargs = mocked_popen.call_args
    assert args[0] == session_start_payload.REFRESH_COMMAND
    assert kwargs["cwd"] == session_start_payload.ROOT
    assert kwargs["stdout"] == session_start_payload.subprocess.DEVNULL
    assert kwargs["stderr"] == session_start_payload.subprocess.DEVNULL


@mock.patch("scripts.session_start_payload.subprocess.Popen")
def test_trigger_refresh_reports_start_failure(mocked_popen, capsys) -> None:
    mocked_popen.side_effect = OSError("missing docker")

    assert not session_start_payload._trigger_refresh()

    assert "missing docker" in capsys.readouterr().err


@mock.patch("scripts.session_start_payload._trigger_refresh")
@mock.patch("scripts.session_start_payload._read_payload")
def test_main_triggers_refresh_when_payload_is_unavailable(mocked_read_payload, mocked_refresh, capsys) -> None:
    mocked_read_payload.side_effect = RuntimeError("helper unavailable")

    with mock.patch("sys.argv", ["session_start_payload.py"]):
        result = session_start_payload.main()

    assert result == 1
    mocked_refresh.assert_called_once()
    assert "helper unavailable" in capsys.readouterr().err


@mock.patch("scripts.session_start_payload._trigger_refresh")
@mock.patch("scripts.session_start_payload._read_payload")
def test_main_triggers_refresh_when_payload_is_nearly_expired(
    mocked_read_payload,
    mocked_refresh,
    capsys,
) -> None:
    mocked_read_payload.return_value = {
        "body": "[HANDOFF READ: ok]",
        "expires_at": "2026-05-26T00:01:00Z",
    }
    mocked_refresh.return_value = True
    with mock.patch("scripts.session_start_payload.datetime") as mocked_datetime:
        mocked_datetime.now.return_value = datetime(
            2026,
            5,
            26,
            0,
            0,
            30,
            tzinfo=timezone.utc,
        )
        mocked_datetime.fromisoformat = datetime.fromisoformat

        with mock.patch("sys.argv", ["session_start_payload.py"]):
            result = session_start_payload.main()

    assert result == 0
    mocked_refresh.assert_called_once()
    assert "[HANDOFF READ: ok]" in capsys.readouterr().out


def test_agent_rule_files_make_cached_payload_the_default() -> None:
    for relative_path in ("AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md", "AI-CONTEXT.md"):
        text = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "python scripts/session_start_payload.py" in text
        assert "refresh_session_start_payload" in text
        assert "Do not run `docker compose exec -T backend python manage.py refresh_session_start_payload` during normal chat startup" in text or "Normal chat startup must not run `docker compose exec -T backend python manage.py refresh_session_start_payload`" in text
        assert "Do not read `audit/session_start_payload.jsonl`" in text or "read `audit/session_start_payload.jsonl`" in text
        assert "only run live startup commands when the user explicitly asks" in text.lower()


def test_agent_rule_files_do_not_tell_agents_to_rerun_after_stale_payload() -> None:
    banned_phrases = (
        "If the payload is stale or missing, run `docker compose exec -T backend python manage.py refresh_session_start_payload`, then run `python scripts/session_start_payload.py` again.",
        "Use those live commands only as fallback evidence when the cached payload is stale or missing.",
        "then run the individual legacy commands so the session still has real marker evidence",
    )

    for relative_path in ("AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md", "AI-CONTEXT.md"):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for phrase in banned_phrases:
            assert phrase not in text


def test_startup_banner_uses_payload_before_legacy_fallback() -> None:
    text = (ROOT / "scripts" / "session-start-banner.ps1").read_text(encoding="utf-8")

    payload_index = text.index("scripts/session_start_payload.py")
    legacy_index = text.index("print_open_issues")

    assert payload_index < legacy_index
    assert "refresh_session_start_payload" in text
