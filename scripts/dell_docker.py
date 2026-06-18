"""Run Docker commands on Dell over SSH, not through MSI Docker."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.remote_docker import build_ssh_docker_command, run_remote_docker

DEFAULT_DELL_HOST = "dell"
DELL_HOST_ENV = "XF_DELL_SSH_HOST"


def run_dell_docker(args: Sequence[str], *, passthrough: bool = False) -> int:
    """Run Docker on Dell and relay stdout and stderr."""
    return run_remote_docker(args, host=DEFAULT_DELL_HOST)


def main(argv: Sequence[str] | None = None) -> int:
    return run_dell_docker(list(sys.argv[1:] if argv is None else argv), passthrough=True)


if __name__ == "__main__":
    raise SystemExit(main())
