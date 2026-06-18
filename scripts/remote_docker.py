"""Run Docker on a remote helper through SSH, never through MSI Docker."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_HOST = "dell"
HOST_ENV = "XF_REMOTE_DOCKER_HOST"
LOCAL_HOSTS = {"__local__", "local"}


def build_ssh_docker_command(args: Sequence[str], *, host: str | None = None) -> list[str]:
    """Build an SSH command that asks a helper host to run Docker."""
    selected_host = host or os.environ.get(HOST_ENV, DEFAULT_HOST)
    if selected_host in LOCAL_HOSTS:
        return ["docker", *args]
    return ["ssh", selected_host, shlex.join(["docker", *args])]


def run_remote_docker(args: Sequence[str], *, host: str | None = None) -> int:
    """Run Docker remotely with inherited input and output streams."""
    try:
        return subprocess.run(build_ssh_docker_command(args, host=host), check=False).returncode
    except FileNotFoundError:
        print("FAIL remote Docker: ssh is not available on MSI.", file=sys.stderr)
        return 127


def _parse_args(argv: Sequence[str]) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(description="Run Docker on a remote helper over SSH.")
    parser.add_argument("--host", default=os.environ.get(HOST_ENV, DEFAULT_HOST))
    parser.add_argument("docker_args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)
    docker_args = list(parsed.docker_args)
    if docker_args[:1] == ["--"]:
        docker_args = docker_args[1:]
    return parsed.host, docker_args


def main(argv: Sequence[str] | None = None) -> int:
    host, docker_args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    return run_remote_docker(docker_args, host=host)


if __name__ == "__main__":
    raise SystemExit(main())
