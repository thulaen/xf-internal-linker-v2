"""Tests for the Bazel default bridge."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _mod():
    path = ROOT / "scripts" / "bazel_default.py"
    spec = importlib.util.spec_from_file_location("bazel_default", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_args_run_quality_suite(monkeypatch):
    mod = _mod()
    captured = {}

    def fake_run_bazel(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(mod, "run_bazel", fake_run_bazel)

    assert mod.main([]) == 0
    assert captured["argv"] == ["test", "//tools/quality:all"]


def test_remote_bazel_syncs_then_runs_quoted_bazel(monkeypatch, tmp_path):
    mod = _mod()
    calls = []
    monkeypatch.setattr(mod, "sync_to_dell", lambda root: calls.append(("sync", root)))
    monkeypatch.setattr(
        mod,
        "_run",
        lambda cmd, cwd=None, env=None, input_text=None: calls.append(("run", cmd, input_text)) or 0,
    )
    monkeypatch.setattr(mod, "changed_paths", lambda root: "backend/example.py\nname with spaces.py")

    assert mod.remote_bazel(["run", "//tools/quality:python"], tmp_path) == 0
    assert calls[0] == ("sync", tmp_path)
    assert calls[1][1] == ["ssh", "dell", "bash", "-s"]
    assert "bazel run //tools/quality:python" in calls[1][2]
    assert "backend/example.py\nname with spaces.py" in calls[1][2]


def test_remote_bazel_script_keeps_multiline_paths_out_of_command_line():
    mod = _mod()

    script = mod._remote_bazel_script(
        workspace="/repo",
        mode="worktree",
        paths="a.py\nb path.py",
        bazel_command="bazel run //tools/quality:python",
    )

    assert "cat <<'XF_BAZEL_SCOPE_PATHS'" in script
    assert "a.py\nb path.py" in script


def test_public_quality_scripts_delegate_to_bazel():
    scripts = {
        ROOT / "scripts" / "run-python-quality.sh": "//tools/quality:python",
        ROOT / "scripts" / "run-angular-quality.sh": "//tools/quality:frontend",
        ROOT / "scripts" / "run-rust-quality.sh": "//tools/quality:rust",
    }
    for script, target in scripts.items():
        text = script.read_text(encoding="utf-8")
        assert "Bazel is the required quality path" in text
        assert f"scripts/bazel_default.py run {target}" in text


def test_bazel_wrappers_call_private_runner_bodies():
    wrappers = {
        ROOT / "tools" / "quality" / "python.sh": "tools/quality/internal/run-python-quality.sh",
        ROOT / "tools" / "quality" / "frontend.sh": "tools/quality/internal/run-angular-quality.sh",
        ROOT / "tools" / "quality" / "rust.sh": "tools/quality/internal/run-rust-quality.sh",
    }
    for wrapper, internal_path in wrappers.items():
        text = wrapper.read_text(encoding="utf-8")
        assert "XF_BAZEL_INTERNAL=1" in text
        assert internal_path in text


def test_bazel_test_gets_workspace_env():
    mod = _mod()
    args = mod.bazel_args_for_workspace(["test", "//tools/quality:all"], "/repo")
    assert args == [
        "test",
        "--test_env=BUILD_WORKSPACE_DIRECTORY=/repo",
        "//tools/quality:all",
    ]


def test_bazel_run_quality_target_gets_repo_root_arg():
    mod = _mod()

    args = mod.bazel_args_for_workspace(["run", "//tools/quality:mutation"], "/repo")

    assert args == ["run", "//tools/quality:mutation", "--", "--repo-root=/repo"]


def test_mutation_target_forces_remote_bazel():
    mod = _mod()

    assert mod.requires_remote_bazel(["run", "//tools/quality:mutation"])
    assert not mod.requires_remote_bazel(["run", "//tools/quality:python"])


def test_bazel_mutation_wrapper_uses_scope_before_running_tools():
    text = (ROOT / "tools" / "quality" / "mutation.sh").read_text(encoding="utf-8")

    assert "COMMIT_SCOPE_PATHS" in text
    assert "No backend Python mutation scope" in text
    assert "No script mutation scope" in text


def test_python_mutation_runner_can_run_from_synced_bazel_copy():
    text = (ROOT / "scripts" / "run-python-mutation.sh").read_text(encoding="utf-8")

    assert "git rev-parse --show-toplevel 2>/dev/null || true" in text
    assert 'dirname "${BASH_SOURCE[0]}")/..' in text


def test_repo_mutation_runner_uses_configured_docker_context_for_probe():
    text = (ROOT / "scripts" / "run-python-repo-mutation.sh").read_text(encoding="utf-8")

    assert 'docker_context_args=(--context "$mutation_context")' in text
    assert '"${docker_cmd[@]}" "${docker_context_args[@]}" version' in text
    assert '"${docker_cmd[@]}" --context dell version' not in text


def test_bazel_env_sets_home_from_windows_userprofile(monkeypatch, tmp_path):
    mod = _mod()
    monkeypatch.setenv("USERPROFILE", r"C:\Users\goldm")
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setattr(mod, "changed_paths", lambda root: "")

    env = mod.bazel_env(tmp_path)

    assert env["HOME"] == r"C:\Users\goldm"


def test_changed_paths_uses_head_when_worktree_is_clean(monkeypatch, tmp_path):
    mod = _mod()
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(tuple(cmd[1:]))
        if cmd[1] == "diff-tree":
            return SimpleNamespace(stdout="scripts/bazel_default.py\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    assert mod.changed_paths(tmp_path) == "scripts/bazel_default.py"
    assert (
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "--diff-filter=ACM",
        "-r",
        "HEAD",
    ) in commands
