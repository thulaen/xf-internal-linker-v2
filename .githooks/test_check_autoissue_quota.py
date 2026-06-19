"""Tests for the combined quota hook used by commit and push."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".githooks" / "check-autoissue-quota.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("check_autoissue_quota", HOOK_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hook_returns_2_when_either_quota_short(monkeypatch, capsys) -> None:
    hook = _load_hook()

    def fake_run(command, **kwargs):
        if "verify_autoissue_quota" in command:
            return subprocess.CompletedProcess(
                command,
                2,
                "",
                "quota: 0 of 10 resolved\n",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            "[PAPER TRAIL QUOTA VERIFIED: 10 resolved]\n",
            "",
        )

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 2
    assert "quota" in capsys.readouterr().err.lower()


def test_hook_returns_zero_when_both_verifiers_pass(monkeypatch) -> None:
    hook = _load_hook()

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 0


def test_hook_runs_quota_verifiers_in_order(monkeypatch) -> None:
    hook = _load_hook()
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 0
    assert "verify_autoissue_quota" in seen[0]
    assert "verify_paper_trail_quota" in seen[1]


def test_hook_passes_commit_cutoff_to_both_verifiers(monkeypatch) -> None:
    hook = _load_hook()
    seen = []
    monkeypatch.setattr(
        hook.commit_quota_state,
        "read_cutoff_for_quota",
        lambda: "2026-06-18 12:34",
    )

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 0
    assert all("--resolved-after" in command for command in seen)
    assert all("2026-06-18 12:34" in command for command in seen)


def test_missing_commit_cutoff_keeps_first_run_behavior(monkeypatch) -> None:
    hook = _load_hook()
    seen = []
    monkeypatch.setattr(
        hook.commit_quota_state,
        "read_cutoff_for_quota",
        lambda: None,
    )

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 0
    assert all("--resolved-after" not in command for command in seen)


def test_broken_commit_cutoff_state_fails_closed(monkeypatch, capsys) -> None:
    hook = _load_hook()

    def fail_cutoff():
        raise hook.commit_quota_state.QuotaStateError("state bad")

    monkeypatch.setattr(hook.commit_quota_state, "read_cutoff_for_quota", fail_cutoff)

    assert hook.main() == 2
    assert "state bad" in capsys.readouterr().err


def test_docker_down_fails_closed(monkeypatch, capsys) -> None:
    hook = _load_hook()

    def fake_run(command, **kwargs):
        raise FileNotFoundError("backend_manage.py")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 2
    assert "Kubernetes backend is unreachable" in capsys.readouterr().err


def test_hook_uses_shared_backend_runner(monkeypatch) -> None:
    hook = _load_hook()
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 0
    assert all(
        "scripts\\backend_manage.py" in command[1]
        or "scripts/backend_manage.py" in command[1]
        for command in seen
    )
    assert all("docker" not in command for command in seen)


def test_fresh_repo_grandfathers(monkeypatch, capsys) -> None:
    hook = _load_hook()

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            "grandfather: no prior session\n",
            "",
        )

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 0
    assert "grandfather: no prior session" in capsys.readouterr().out


def test_ci_mode_does_not_bypass(monkeypatch) -> None:
    hook = _load_hook()
    monkeypatch.setenv("XF_QUALITY_ENV", "ci")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            2,
            "",
            "paper-trail: 6 of 10 resolved (4 short)\n",
        )

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.main() == 2


def test_pre_commit_enforces_both_quotas() -> None:
    precommit = (REPO_ROOT / "scripts" / "precommit-docker.sh").read_text(encoding="utf-8")

    quota_index = precommit.index("python .githooks/check-autoissue-quota.py")
    quality_index = precommit.index("//tools/quality:tool_readiness")

    assert quality_index < quota_index


def test_pre_commit_records_quota_reset_after_staged_files() -> None:
    precommit = (REPO_ROOT / "scripts" / "precommit-docker.sh").read_text(encoding="utf-8")

    assert "quota_reset_enabled=1" in precommit
    assert ".githooks/commit_quota_state.py record-failure" in precommit
    assert precommit.index("quota_reset_enabled=1") < precommit.index(
        "run_hard_gate verify-deep-links"
    )


def test_post_commit_records_successful_quota_reset() -> None:
    postcommit = (REPO_ROOT / ".githooks" / "post-commit").read_text(encoding="utf-8")

    assert ".githooks/commit_quota_state.py record-success --commit" in postcommit


# --- 2026-05-29 regression tests: the verifiers expose --session-type, not the
#     long-removed --since-handoff.


def test_source_uses_session_type_not_since_handoff() -> None:
    src = HOOK_PATH.read_text(encoding="utf-8")
    assert "--since-handoff" not in src, (
        "verify_autoissue_quota/verify_paper_trail_quota have no --since-handoff "
        "argument; the hook must pass the --session-type interface they expose"
    )
    assert "--session-type" in src


def test_session_type_reads_gate_state(tmp_path, monkeypatch) -> None:
    import json

    hook = _load_hook()
    state = tmp_path / "session_gate_state.json"
    state.write_text(json.dumps({"session_type": "reconciliation"}), encoding="utf-8")
    monkeypatch.setattr(hook, "GATE_STATE", state)
    assert hook._session_type() == "reconciliation"


def test_session_type_defaults_to_feature_when_missing_or_garbled(tmp_path, monkeypatch) -> None:
    hook = _load_hook()
    monkeypatch.setattr(hook, "GATE_STATE", tmp_path / "nope.json")
    assert hook._session_type() == "feature"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(hook, "GATE_STATE", bad)
    assert hook._session_type() == "feature"


def test_session_type_rejects_unknown_value(tmp_path, monkeypatch) -> None:
    import json

    hook = _load_hook()
    state = tmp_path / "session_gate_state.json"
    state.write_text(json.dumps({"session_type": "banana"}), encoding="utf-8")
    monkeypatch.setattr(hook, "GATE_STATE", state)
    assert hook._session_type() == "feature"
