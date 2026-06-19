#!/usr/bin/env python3
"""Run the repo's default quality commands through Dell-backed Bazel."""

from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import dell_ssh_preflight
except ImportError:
    from scripts import dell_ssh_preflight


REMOTE_HOST = os.environ.get("XF_BAZEL_HOST", "dell")
REMOTE_ROOT = os.environ.get("XF_BAZEL_REMOTE_ROOT", "/tmp/xf-bazel-default-repo")
BAZEL_PARALLEL_ARGS = ["--jobs=HOST_CPUS", "--local_resources=cpu=HOST_CPUS"]
BAZEL_TEST_PARALLEL_ARGS = ["--local_test_jobs=HOST_CPUS"]
QUALITY_CORE_ENV_KEYS = (
    "XF_QUALITY_CORES",
    "ANGULAR_CORES",
    "XF_RUST_MUTATION_JOBS",
    "XF_MUTMUT_CHILDREN",
)


def repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=True,
    )
    return Path(result.stdout.strip())


def local_bazel() -> str | None:
    return shutil.which("bazel") or shutil.which("bazelisk")


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> int:
    if input_text is None:
        return subprocess.run(cmd, cwd=cwd, env=env, check=False).returncode
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text.encode("utf-8"),
        check=False,
    ).returncode


def changed_paths(root: Path) -> str:
    commands = (
        ("diff", "--cached", "--name-only", "--diff-filter=ACM"),
        ("diff", "--name-only", "--diff-filter=ACM", "HEAD"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            ["git", *command],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        paths.update(
            path
            for raw_path in result.stdout.splitlines()
            if (path := _existing_source_path(root, raw_path)) is not None
        )
    return "\n".join(sorted(path for path in paths if path))


def source_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return sorted(
        path
        for raw_path in result.stdout.splitlines()
        if (path := _existing_source_path(root, raw_path)) is not None
    )


def _existing_source_path(root: Path, raw_path: str) -> str | None:
    path = raw_path.strip().replace("\\", "/")
    if not path:
        return None
    if not (root / path).is_file():
        return None
    return path


def should_use_remote_bazel(local_bazel_path: str | None) -> bool:
    if os.environ.get("XF_BAZEL_FORCE_LOCAL") == "1" and local_bazel_path:
        return False
    if platform.system() == "Windows" and os.environ.get("CI") != "true":
        return True
    return local_bazel_path is None


def default_worker_count() -> str:
    override = os.environ.get("XF_QUALITY_CORES")
    if override:
        return override
    try:
        from scripts.quality_cores import quality_cores

        return str(quality_cores("bazel").workers)
    except Exception:
        return str(max(1, os.cpu_count() or 1))


def bazel_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    if "HOME" not in env and env.get("USERPROFILE"):
        env["HOME"] = env["USERPROFILE"]
    env["BUILD_WORKSPACE_DIRECTORY"] = str(root)
    env["REPO_ROOT"] = str(root)
    env.setdefault("COMMIT_SCOPE_MODE", "worktree")
    env["COMMIT_SCOPE_PATHS"] = changed_paths(root)
    workers = env.setdefault("XF_QUALITY_CORES", default_worker_count())
    env.setdefault("ANGULAR_CORES", workers)
    env.setdefault("XF_RUST_MUTATION_JOBS", workers)
    env.setdefault("XF_MUTMUT_CHILDREN", workers)
    return env


def bazel_args_for_workspace(argv: list[str], workspace: str) -> list[str]:
    if argv and argv[0] == "test":
        return [
            argv[0],
            *BAZEL_PARALLEL_ARGS,
            *BAZEL_TEST_PARALLEL_ARGS,
            f"--test_env=BUILD_WORKSPACE_DIRECTORY={workspace}",
            f"--test_env=REPO_ROOT={workspace}",
            *[f"--test_env={key}" for key in QUALITY_CORE_ENV_KEYS],
            *argv[1:],
        ]
    if argv and argv[0] == "run":
        return bazel_run_args_for_workspace(argv, workspace)
    return argv


def bazel_run_args_for_workspace(argv: list[str], workspace: str) -> list[str]:
    """Add a repo-root runtime argument to a `bazel run` command."""
    if len(argv) < 2:
        return argv
    rest = argv[1:]
    if "--" in rest:
        separator_index = rest.index("--")
        before_separator = rest[:separator_index]
        after_separator = rest[separator_index + 1 :]
    else:
        before_separator = rest
        after_separator = []
    return [
        "run",
        *BAZEL_PARALLEL_ARGS,
        *before_separator,
        "--",
        f"--repo-root={workspace}",
        *after_separator,
    ]


def run_bazel(argv: list[str]) -> int:
    root = repo_root()
    bazel = local_bazel()
    env = bazel_env(root)
    if not should_use_remote_bazel(bazel):
        bazel_args = bazel_args_for_workspace(argv, str(root))
        return _run([bazel, *bazel_args], cwd=root, env=env)
    return remote_bazel(argv, root, env)


def sync_to_dell(root: Path) -> None:
    dell_ssh_preflight.require_dell_ssh_ready(REMOTE_HOST)
    ssh_command = dell_ssh_preflight.ssh_base_command(REMOTE_HOST)
    remote_cmd = (
        f"rm -rf {shlex.quote(REMOTE_ROOT)} && "
        f"mkdir -p {shlex.quote(REMOTE_ROOT)} && "
        f"tar -xf - -C {shlex.quote(REMOTE_ROOT)} && "
        f"find {shlex.quote(REMOTE_ROOT)} -name '*.sh' -exec chmod +x {{}} +"
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write("\n".join(source_files(root)))
        handle.write("\n")
        list_path = handle.name
    try:
        tar_proc = subprocess.Popen(
            ["tar", "-cf", "-", "-T", list_path],
            cwd=root,
            stdout=subprocess.PIPE,
        )
        sink = subprocess.Popen(
            [*ssh_command, remote_cmd],
            stdin=tar_proc.stdout,
        )
        if tar_proc.stdout:
            tar_proc.stdout.close()
        sink_rc = sink.wait()
        tar_rc = tar_proc.wait()
        if tar_rc or sink_rc:
            raise SystemExit(f"Bazel source sync to {REMOTE_HOST} failed.")
    finally:
        Path(list_path).unlink(missing_ok=True)


def remote_bazel(argv: list[str], root: Path, env: dict[str, str]) -> int:
    sync_to_dell(root)
    ssh_command = dell_ssh_preflight.ssh_base_command(REMOTE_HOST)
    bazel_args = bazel_args_for_workspace(argv, REMOTE_ROOT)
    quoted = " ".join(shlex.quote(part) for part in ["bazel", *bazel_args])
    script = _remote_bazel_script(env=env, bazel_command=quoted)
    return _run([*ssh_command, "bash", "-s"], input_text=script)


def _remote_bazel_script(*, env: dict[str, str], bazel_command: str) -> str:
    exports = {
        "BUILD_WORKSPACE_DIRECTORY": REMOTE_ROOT,
        "REPO_ROOT": REMOTE_ROOT,
        "COMMIT_SCOPE_MODE": env["COMMIT_SCOPE_MODE"],
        "COMMIT_SCOPE_PATHS": env["COMMIT_SCOPE_PATHS"],
    }
    for key in QUALITY_CORE_ENV_KEYS:
        exports[key] = env[key]
    return "\n".join(
        [
            "set -euo pipefail",
            f"cd {shlex.quote(REMOTE_ROOT)}",
            *[
                f"export {key}={shlex.quote(value)}"
                for key, value in exports.items()
                if key != "COMMIT_SCOPE_PATHS"
            ],
            "COMMIT_SCOPE_PATHS=$(cat <<'XF_BAZEL_SCOPE_PATHS'",
            exports["COMMIT_SCOPE_PATHS"],
            "XF_BAZEL_SCOPE_PATHS",
            ")",
            "export COMMIT_SCOPE_PATHS",
            f"exec {bazel_command}",
        ]
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Bazel locally.")
    parser.add_argument("bazel_args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    bazel_args = args.bazel_args
    if bazel_args and bazel_args[0] == "--":
        bazel_args = bazel_args[1:]
    if not bazel_args:
        bazel_args = ["test", "//tools/quality:all"]
    return run_bazel(bazel_args)


if __name__ == "__main__":
    raise SystemExit(main())
