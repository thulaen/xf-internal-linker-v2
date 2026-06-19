"""Tests for the Bazel default bridge."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _mod():
    sys.modules.pop("scripts.bazel_default", None)
    mod = importlib.import_module("scripts.bazel_default")
    assert Path(mod.__file__).resolve() == ROOT / "scripts" / "bazel_default.py"
    return mod


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    bash = shutil.which("bash")
    assert bash is not None
    return bash


def _make_mutation_stub_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    quality_dir = repo / "tools" / "quality"
    quality_dir.mkdir(parents=True)
    log_path = tmp_path / "mutation.log"
    (quality_dir / "mutation.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return repo, log_path


def _mutation_env(log_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("BUILD_WORKSPACE_DIRECTORY", None)
    env.pop("REPO_ROOT", None)
    env["MUTATION_LOG"] = str(log_path)
    return env


def test_default_args_run_quality_suite(monkeypatch):
    mod = _mod()
    captured = {}

    def fake_run_bazel(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(mod, "run_bazel", fake_run_bazel)

    assert mod.main([]) == 0
    assert captured["argv"] == ["test", "//tools/quality:all"]


def test_repo_root_reads_git_top_level(monkeypatch, tmp_path):
    mod = _mod()
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=str(tmp_path) + "\n"),
    )

    assert mod.repo_root() == tmp_path


def test_local_bazel_prefers_bazel_then_bazelisk(monkeypatch):
    mod = _mod()
    calls: list[str] = []

    def fake_which(name: str) -> str | None:
        calls.append(name)
        return "bazel.exe" if name == "bazel" else "bazelisk.exe"

    monkeypatch.setattr(mod.shutil, "which", fake_which)
    assert mod.local_bazel() == "bazel.exe"
    assert calls == ["bazel"]

    monkeypatch.setattr(mod.shutil, "which", lambda name: "bazelisk.exe" if name == "bazelisk" else None)
    assert mod.local_bazel() == "bazelisk.exe"


def test_msi_uses_remote_bazel_even_when_local_bazel_exists(monkeypatch):
    mod = _mod()
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.delenv("CI", raising=False)

    assert mod.should_use_remote_bazel("bazel.exe")


def test_force_local_allows_local_bazel(monkeypatch):
    mod = _mod()
    monkeypatch.setenv("XF_BAZEL_FORCE_LOCAL", "1")
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")

    assert not mod.should_use_remote_bazel("bazel.exe")


def test_run_handles_plain_and_stdin_commands(monkeypatch):
    mod = _mod()
    calls: list[dict[str, object]] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    assert mod._run(["echo", "ok"]) == 7
    assert mod._run(["cat"], input_text="hello") == 7
    assert calls[1]["input"] == b"hello"


def test_changed_paths_merges_git_outputs(monkeypatch, tmp_path):
    mod = _mod()
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "c.py").write_text("", encoding="utf-8")
    (tmp_path / "new.py").write_text("", encoding="utf-8")
    outputs = iter(["b.py\na.py\n", "a.py\nc.py\n", "new.py\n"])

    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=next(outputs)),
    )

    assert mod.changed_paths(tmp_path) == "a.py\nb.py\nc.py\nnew.py"


def test_changed_paths_filters_missing_and_normalizes(monkeypatch, tmp_path):
    mod = _mod()
    nested = tmp_path / "scripts"
    nested.mkdir()
    (nested / "tool.py").write_text("", encoding="utf-8")
    outputs = iter(["scripts\\tool.py\nmissing.py\n\n", "", ""])

    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=next(outputs)),
    )

    assert mod.changed_paths(tmp_path) == "scripts/tool.py"


def test_source_files_filters_missing_and_normalizes(monkeypatch, tmp_path):
    mod = _mod()
    nested = tmp_path / "scripts"
    nested.mkdir()
    (nested / "tool.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="scripts\\tool.py\nmissing.py\n\n"
        ),
    )

    assert mod.source_files(tmp_path) == ["scripts/tool.py"]


def test_public_quality_scripts_are_deleted():
    for script in (
        ROOT / "scripts" / "run-python-quality.sh",
        ROOT / "scripts" / "run-angular-quality.sh",
        ROOT / "scripts" / "run-rust-quality.sh",
        ROOT / "scripts" / "run-scoped-static-quality.ps1",
    ):
        assert not script.exists()


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
        "--jobs=HOST_CPUS",
        "--local_resources=cpu=HOST_CPUS",
        "--local_test_jobs=HOST_CPUS",
        "--test_env=BUILD_WORKSPACE_DIRECTORY=/repo",
        "--test_env=REPO_ROOT=/repo",
        "--test_env=XF_QUALITY_CORES",
        "--test_env=ANGULAR_CORES",
        "--test_env=XF_RUST_MUTATION_JOBS",
        "--test_env=XF_MUTMUT_CHILDREN",
        "//tools/quality:all",
    ]


def test_bazelrc_uses_visible_host_cpus_not_fixed_cpu_cap():
    text = (ROOT / ".bazelrc").read_text(encoding="utf-8")

    assert "build --local_resources=cpu=12" not in text
    assert "build --jobs=HOST_CPUS" in text
    assert "build --local_resources=cpu=HOST_CPUS" in text
    assert "test --local_test_jobs=HOST_CPUS" in text


def test_bazel_env_sets_home_from_windows_userprofile(monkeypatch, tmp_path):
    mod = _mod()
    monkeypatch.setenv("USERPROFILE", r"C:\Users\goldm")
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setattr(mod, "changed_paths", lambda root: "")
    monkeypatch.setattr(mod, "default_worker_count", lambda: "20")

    env = mod.bazel_env(tmp_path)

    assert env["HOME"] == r"C:\Users\goldm"
    assert env["BUILD_WORKSPACE_DIRECTORY"] == str(tmp_path)
    assert env["REPO_ROOT"] == str(tmp_path)
    assert env["XF_QUALITY_CORES"] == "20"
    assert env["ANGULAR_CORES"] == "20"
    assert env["XF_RUST_MUTATION_JOBS"] == "20"
    assert env["XF_MUTMUT_CHILDREN"] == "20"


def test_bazel_run_gets_workspace_environment(monkeypatch, tmp_path):
    mod = _mod()
    captured = {}
    monkeypatch.setenv("XF_BAZEL_FORCE_LOCAL", "1")
    monkeypatch.setattr(mod, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "local_bazel", lambda: "bazel")
    monkeypatch.setattr(mod, "changed_paths", lambda root: "")
    monkeypatch.setattr(
        mod,
        "_run",
        lambda cmd, cwd=None, env=None, input_text=None: captured.update(
            {"cmd": cmd, "cwd": cwd, "env": env}
        )
        or 0,
    )

    assert mod.run_bazel(["run", "//tools/quality:mutation"]) == 0
    assert captured["cmd"] == [
        "bazel",
        "run",
        "--jobs=HOST_CPUS",
        "--local_resources=cpu=HOST_CPUS",
        "//tools/quality:mutation",
        "--",
        f"--repo-root={tmp_path}",
    ]
    assert captured["cwd"] == tmp_path
    assert captured["env"]["BUILD_WORKSPACE_DIRECTORY"] == str(tmp_path)
    assert captured["env"]["REPO_ROOT"] == str(tmp_path)


def test_remote_bazel_syncs_then_runs_quoted_bazel(monkeypatch, tmp_path):
    mod = _mod()
    calls = []
    env = {
        "BUILD_WORKSPACE_DIRECTORY": str(tmp_path),
        "REPO_ROOT": str(tmp_path),
        "COMMIT_SCOPE_MODE": "worktree",
        "COMMIT_SCOPE_PATHS": "backend/example.py\nname with spaces.py",
        "XF_QUALITY_CORES": "20",
        "ANGULAR_CORES": "20",
        "XF_RUST_MUTATION_JOBS": "20",
        "XF_MUTMUT_CHILDREN": "20",
    }
    monkeypatch.setattr(mod, "sync_to_dell", lambda root: calls.append(("sync", root)))
    monkeypatch.setattr(
        mod.dell_ssh_preflight,
        "ssh_base_command",
        lambda host: [
            "ssh",
            "-o",
            "ProxyCommand=ssh -o BatchMode=yes -W %h:%p mint-wifi",
            "dell-ubuntu-01@10.10.10.92",
        ],
    )
    monkeypatch.setattr(
        mod,
        "_run",
        lambda cmd, cwd=None, env=None, input_text=None: calls.append(
            ("run", cmd, input_text)
        )
        or 0,
    )

    assert mod.remote_bazel(["run", "//tools/quality:python"], tmp_path, env) == 0
    assert calls[0] == ("sync", tmp_path)
    assert calls[1][1] == [
        "ssh",
        "-o",
        "ProxyCommand=ssh -o BatchMode=yes -W %h:%p mint-wifi",
        "dell-ubuntu-01@10.10.10.92",
        "bash",
        "-s",
    ]
    assert "bazel run" in calls[1][2]
    assert "backend/example.py\nname with spaces.py" in calls[1][2]


def test_sync_to_dell_checks_ssh_before_tar(monkeypatch, tmp_path):
    mod = _mod()
    calls: list[str] = []

    def fail_preflight(host):
        calls.append(host)
        raise SystemExit(2)

    monkeypatch.setattr(mod.dell_ssh_preflight, "require_dell_ssh_ready", fail_preflight)
    monkeypatch.setattr(
        mod.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("source sync must not start when Dell SSH is unhealthy")
        ),
    )

    try:
        mod.sync_to_dell(tmp_path)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("sync_to_dell should stop on Dell SSH preflight failure")

    assert calls == ["dell"]


def test_bazel_run_preserves_existing_binary_args():
    mod = _mod()
    args = mod.bazel_args_for_workspace(
        ["run", "//tools/quality:mutation", "--", "--changed-only"],
        "/repo",
    )

    assert args == [
        "run",
        "--jobs=HOST_CPUS",
        "--local_resources=cpu=HOST_CPUS",
        "//tools/quality:mutation",
        "--",
        "--repo-root=/repo",
        "--changed-only",
    ]


def test_bazel_args_pass_through_unknown_command():
    mod = _mod()

    assert mod.bazel_args_for_workspace(["query", "//tools/quality:all"], "/repo") == [
        "query",
        "//tools/quality:all",
    ]
    assert mod.bazel_run_args_for_workspace(["run"], "/repo") == ["run"]


def test_run_bazel_uses_remote_when_local_bazel_missing(monkeypatch, tmp_path):
    mod = _mod()
    captured = {}
    monkeypatch.setattr(mod, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "local_bazel", lambda: None)
    monkeypatch.setattr(mod, "changed_paths", lambda root: "")
    monkeypatch.setattr(mod, "default_worker_count", lambda: "20")
    monkeypatch.setattr(
        mod,
        "remote_bazel",
        lambda argv, root, env: captured.update(
            {"argv": argv, "root": root, "env": env}
        )
        or 0,
    )

    assert mod.run_bazel(["test", "//tools/quality:all"]) == 0
    assert captured["root"] == tmp_path
    assert captured["argv"] == ["test", "//tools/quality:all"]
    assert captured["env"]["XF_QUALITY_CORES"] == "20"


def test_main_strips_leading_separator(monkeypatch):
    mod = _mod()
    captured = {}
    monkeypatch.setattr(mod, "run_bazel", lambda argv: captured.update({"argv": argv}) or 0)

    assert mod.main(["--", "run", "//tools/quality:python"]) == 0
    assert captured["argv"] == ["run", "//tools/quality:python"]


def test_provider_score_backend_wrapper_sets_django_test_defaults():
    wrapper = (ROOT / "tools" / "quality" / "provider_score_backend.sh").read_text(
        encoding="utf-8"
    )

    assert 'export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.test}"' in wrapper
    assert 'export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-ci-fake-secret-key}"' in wrapper
    assert 'export XF_USE_POSTGRES_TEST_DB="${XF_USE_POSTGRES_TEST_DB:-1}"' in wrapper


def test_mutation_wrapper_uses_repo_root_argument(tmp_path):
    repo, log_path = _make_mutation_stub_repo(tmp_path)

    result = subprocess.run(
        [
            _bash(),
            str(ROOT / "tools" / "quality" / "mutation.sh"),
            f"--repo-root={repo.as_posix()}",
            "--changed-only",
        ],
        check=True,
        cwd=tmp_path,
        env=_mutation_env(log_path),
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert "Docker-backed mutation runners are retired" in result.stdout
    assert "Requested args: --changed-only" in result.stdout
    assert repo.as_posix() not in result.stdout


def test_mutation_wrapper_skips_invalid_workspace_env(tmp_path):
    repo, log_path = _make_mutation_stub_repo(tmp_path)
    invalid_workspace = tmp_path / "not-the-repo"
    invalid_workspace.mkdir()
    env = _mutation_env(log_path)
    env["BUILD_WORKSPACE_DIRECTORY"] = invalid_workspace.as_posix()
    env["REPO_ROOT"] = repo.as_posix()

    result = subprocess.run(
        [_bash(), str(ROOT / "tools" / "quality" / "mutation.sh"), "--changed-only"],
        check=True,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert "Docker-backed mutation runners are retired" in result.stdout
    assert "Requested args: --changed-only" in result.stdout


def test_mutation_wrapper_does_not_export_docker_context_when_git_metadata_exists(tmp_path):
    repo, log_path = _make_mutation_stub_repo(tmp_path)
    (repo / ".git").mkdir()

    result = subprocess.run(
        [_bash(), str(ROOT / "tools" / "quality" / "mutation.sh"), f"--repo-root={repo.as_posix()}"],
        check=True,
        cwd=tmp_path,
        env=_mutation_env(log_path),
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert "Docker-backed mutation runners are retired" in result.stdout
    assert "DOCKER_CONTEXT" not in result.stdout
