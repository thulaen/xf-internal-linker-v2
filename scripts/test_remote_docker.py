"""Tests for the generic SSH-backed remote Docker helper."""

from __future__ import annotations

from scripts import remote_docker


def test_builds_ssh_docker_command() -> None:
    assert remote_docker.build_ssh_docker_command(["ps"], host="dell") == [
        "ssh",
        "dell",
        "docker ps",
    ]


def test_local_host_uses_direct_docker_command() -> None:
    assert remote_docker.build_ssh_docker_command(["ps"], host="__local__") == [
        "docker",
        "ps",
    ]


def test_cli_accepts_host_and_separator() -> None:
    host, args = remote_docker._parse_args(["--host", "mint", "--", "compose", "ps"])

    assert host == "mint"
    assert args == ["compose", "ps"]


def test_ssh_command_quotes_shell_fragments_as_one_remote_command() -> None:
    command = remote_docker.build_ssh_docker_command(
        ["run", "--rm", "alpine:latest", "sh", "-c", "mkdir -p /repo && tar -xf - -C /repo"],
        host="dell",
    )

    assert command == [
        "ssh",
        "dell",
        "docker run --rm alpine:latest sh -c 'mkdir -p /repo && tar -xf - -C /repo'",
    ]
