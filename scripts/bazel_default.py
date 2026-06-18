#!/usr/bin/env python3
"""Run the repo's default quality commands through Bazel on Dell."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REMOTE_HOST = os.environ.get("XF_BAZEL_HOST", "dell")
REMOTE_ROOT = os.environ.get("XF_BAZEL_REMOTE_ROOT", "/tmp/xf-bazel-default-repo")
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


def source_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return sorted(
        path.replace("\\", "/")
        for path in result.stdout.splitlines()
        if path.strip() and (root / path).is_file()
    )


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
        paths.update(path.strip().replace("\\", "/") for path in result.stdout.splitlines())
    return "\n".join(sorted(path for path in paths if path))


def bazel_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    if "HOME" not in env and env.get("USERPROFILE"):
        env["HOME"] = env["USERPROFILE"]
    env.setdefault("COMMIT_SCOPE_MODE", "worktree")
    env["COMMIT_SCOPE_PATHS"] = changed_paths(root)
    return env


def sync_to_dell(root: Path) -> None:
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
        tar_cmd = ["tar", "-cf", "-", "-T", list_path]
        tar_proc = subprocess.Popen(tar_cmd, cwd=root, stdout=subprocess.PIPE)
        sink = subprocess.Popen(
            ["ssh", REMOTE_HOST, remote_cmd],
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


def remote_bazel(argv: list[str], root: Path) -> int:
    sync_to_dell(root)
    env = bazel_env(root)
    bazel_args = bazel_args_for_workspace(argv, REMOTE_ROOT)
    quoted = " ".join(shlex.quote(part) for part in ["bazel", *bazel_args])
    script = _remote_bazel_script(
        workspace=REMOTE_ROOT,
        mode=env["COMMIT_SCOPE_MODE"],
        paths=env["COMMIT_SCOPE_PATHS"],
        bazel_command=quoted,
    )
    return _run(["ssh", REMOTE_HOST, "bash", "-s"], input_text=script)


def _remote_bazel_script(*, workspace: str, mode: str, paths: str, bazel_command: str) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            f"cd {shlex.quote(workspace)}",
            f"export COMMIT_SCOPE_MODE={shlex.quote(mode)}",
            "COMMIT_SCOPE_PATHS=$(cat <<'XF_BAZEL_SCOPE_PATHS'",
            paths,
            "XF_BAZEL_SCOPE_PATHS",
            ")",
            "export COMMIT_SCOPE_PATHS",
            f"exec {bazel_command}",
        ]
    )


def bazel_args_for_workspace(argv: list[str], workspace: str) -> list[str]:
    if argv and argv[0] == "test":
        return [argv[0], f"--test_env=BUILD_WORKSPACE_DIRECTORY={workspace}", *argv[1:]]
    return argv


def run_bazel(argv: list[str]) -> int:
    root = repo_root()
    bazel = local_bazel()
    env = bazel_env(root)
    if bazel:
        bazel_args = bazel_args_for_workspace(argv, str(root))
        return _run([bazel, *bazel_args], cwd=root, env=env)
    return remote_bazel(argv, root)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Bazel locally or on Dell.")
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
