#!/usr/bin/env python3
"""Check Dell SSH readiness before quality tools copy source files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import os
from pathlib import Path
import socket
import subprocess
import sys


DEFAULT_HOST = "dell"
DEFAULT_PORT = 22
TCP_TIMEOUT_SECONDS = 3.0
SSH_TIMEOUT_SECONDS = 60
WINDOWS_PROXY_SHELL = Path("C:/Program Files/Git/bin/bash.exe")


@dataclass(frozen=True)
class DellSshStatus:
    label: str
    host: str
    address: str
    port: int
    ok: bool
    detail: str
    next_action: str

    def line(self) -> str:
        state = "OK" if self.ok else "FAIL"
        return (
            f"{state}: {self.label} "
            f"(host={self.host} address={self.address} port={self.port}). "
            f"{self.detail} NEXT: {self.next_action}"
        )


@dataclass(frozen=True)
class SshConfig:
    address: str
    port: int
    proxy: str | None
    proxy_target: str | None
    user: str | None
    identity_file: str | None


def _ssh_config(host: str) -> SshConfig:
    stdout = _ssh_config_stdout(host)
    if stdout is None:
        return _default_ssh_config(host)
    return _parse_ssh_config(host, stdout)


def _ensure_windows_proxy_shell() -> None:
    if os.name != "nt" or not WINDOWS_PROXY_SHELL.exists():
        return
    current_shell = os.environ.get("SHELL", "").replace("\\", "/").lower()
    if current_shell.endswith("bash.exe") or current_shell.endswith("/bash"):
        return
    os.environ["SHELL"] = str(WINDOWS_PROXY_SHELL)


def _default_ssh_config(host: str) -> SshConfig:
    return SshConfig(host, DEFAULT_PORT, None, None, None, None)


def _ssh_config_stdout(host: str) -> str | None:
    try:
        result = subprocess.run(
            ["ssh", "-G", host],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout


def _parse_ssh_config(host: str, stdout: str) -> SshConfig:
    config = _default_ssh_config(host)
    for line in stdout.splitlines():
        config = _apply_config_line(config, line)
    return config


def _apply_config_line(config: SshConfig, line: str) -> SshConfig:
    key, _, value = line.partition(" ")
    value = value.strip()
    if not _ssh_value_enabled(value):
        return config
    handler = _CONFIG_LINE_HANDLERS.get(key)
    return handler(config, value) if handler else config


def _apply_hostname(config: SshConfig, value: str) -> SshConfig:
    return replace(config, address=value)


def _apply_user(config: SshConfig, value: str) -> SshConfig:
    return replace(config, user=value)


def _apply_identity_file(config: SshConfig, value: str) -> SshConfig:
    return config if config.identity_file else replace(config, identity_file=value)


def _apply_port(config: SshConfig, value: str) -> SshConfig:
    return replace(config, port=int(value)) if value.isdigit() else config


def _apply_proxyjump(config: SshConfig, value: str) -> SshConfig:
    return replace(config, proxy=value, proxy_target=value.split(",", maxsplit=1)[0])


def _apply_proxycommand(config: SshConfig, value: str) -> SshConfig:
    return replace(config, proxy=value, proxy_target=_proxycommand_target(value))


_CONFIG_LINE_HANDLERS = {
    "hostname": _apply_hostname,
    "user": _apply_user,
    "identityfile": _apply_identity_file,
    "port": _apply_port,
    "proxyjump": _apply_proxyjump,
    "proxycommand": _apply_proxycommand,
}


def _ssh_value_enabled(value: str) -> bool:
    return bool(value) and value.lower() != "none"


def _proxycommand_target(proxycommand: str) -> str | None:
    parts = proxycommand.strip().split()
    if "-W" not in parts or len(parts) < 2:
        return None
    return parts[-1]


def _tcp_open(address: str, port: int, timeout_seconds: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((address, port), timeout=timeout_seconds):
            return True, "TCP connection accepted."
    except OSError as exc:
        return False, str(exc)


def _ssh_login_status(
    host: str,
    timeout_seconds: int,
    config: SshConfig,
) -> tuple[str, str]:
    if config.proxy_target:
        fallback = _explicit_jump_command(config, timeout_seconds)
        if fallback is not None:
            fallback_status, fallback_detail = _run_ssh_login(fallback, timeout_seconds)
            if fallback_status == "reachable":
                return fallback_status, f"{fallback_detail} Used explicit jump-host fallback."
            return fallback_status, fallback_detail
    status, detail = _run_ssh_login(_ssh_login_command(host, timeout_seconds), timeout_seconds)
    return status, detail


def _ssh_login_command(host: str, timeout_seconds: int) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout_seconds}",
        "-o",
        "ConnectionAttempts=1",
        "-tt",
        host,
        "true",
    ]


def _explicit_jump_command(config: SshConfig, timeout_seconds: int) -> list[str] | None:
    base = ssh_base_command_from_config(config, timeout_seconds=timeout_seconds)
    if base is None:
        return None
    return [*base[:-1], "-tt", base[-1], "true"]


def ssh_base_command(host: str = DEFAULT_HOST) -> list[str]:
    _ensure_windows_proxy_shell()
    config = _ssh_config(host)
    return ssh_base_command_from_config(config) or ["ssh", host]


def ssh_base_command_from_config(
    config: SshConfig,
    *,
    timeout_seconds: int = SSH_TIMEOUT_SECONDS,
) -> list[str] | None:
    if not config.proxy_target or not config.user:
        return None
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout_seconds}",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        f"ProxyCommand=ssh -o BatchMode=yes -W %h:%p {config.proxy_target}",
    ]
    if config.identity_file:
        command.extend(["-i", str(Path(config.identity_file).expanduser())])
    command.append(f"{config.user}@{config.address}")
    return command


def _run_ssh_login(cmd: list[str], timeout_seconds: int) -> tuple[str, str]:
    _ensure_windows_proxy_shell()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 2,
            check=False,
        )
    except FileNotFoundError:
        return "ssh-missing", "ssh was not found on PATH."
    except subprocess.TimeoutExpired:
        return "banner-timeout", "SSH command timed out before login completed."
    return _classify_ssh_result(result)


def _classify_ssh_result(result: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        return "reachable", output.strip() or "SSH login succeeded."
    detail = output.strip() or f"ssh exited with {result.returncode}."
    return _classify_ssh_error(output, detail)


def _classify_ssh_error(output: str, detail: str) -> tuple[str, str]:
    if "timed out during banner exchange" in output.lower():
        return "banner-timeout", detail
    return "login-failed", detail


def check_dell_ssh(
    host: str = DEFAULT_HOST,
    *,
    tcp_timeout_seconds: float = TCP_TIMEOUT_SECONDS,
    ssh_timeout_seconds: int = SSH_TIMEOUT_SECONDS,
) -> DellSshStatus:
    config = _ssh_config(host)
    tcp_ok, tcp_detail = _tcp_status(config, tcp_timeout_seconds)
    if not tcp_ok:
        return _status_for_tcp_failure(host, config, tcp_detail)
    ssh_status, detail = _ssh_login_status(host, ssh_timeout_seconds, config)
    return _status_for_login(host, config, ssh_status, detail)


def _tcp_status(config: SshConfig, timeout_seconds: float) -> tuple[bool, str]:
    if config.proxy:
        return True, f"SSH uses jump host {config.proxy}; direct TCP check skipped."
    return _tcp_open(config.address, config.port, timeout_seconds)


def _status_for_tcp_failure(host: str, config: SshConfig, detail: str) -> DellSshStatus:
    return DellSshStatus(
        "Dell port closed",
        host,
        config.address,
        config.port,
        False,
        detail,
        "Check Dell power, Wi-Fi, and the IP reservation.",
    )


def _status_for_login(
    host: str,
    config: SshConfig,
    ssh_status: str,
    detail: str,
) -> DellSshStatus:
    if ssh_status == "reachable":
        return DellSshStatus(
            "Dell reachable",
            host,
            config.address,
            config.port,
            True,
            detail,
            "Retry the quality command.",
        )
    if ssh_status == "banner-timeout":
        return DellSshStatus(
            "Dell SSH banner timeout",
            host,
            config.address,
            config.port,
            False,
            detail,
            "Restart Dell's SSH service or reboot Dell, then retry.",
        )
    return DellSshStatus(
        "Dell login failed",
        host,
        config.address,
        config.port,
        False,
        detail,
        "Check ~/.ssh/config, ~/.ssh/dell_xf, and the Dell user.",
    )


def require_dell_ssh_ready(host: str = DEFAULT_HOST) -> None:
    status = check_dell_ssh(host)
    if status.ok:
        return
    print(status.line(), file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Dell SSH before quality work.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--tcp-timeout", type=float, default=TCP_TIMEOUT_SECONDS)
    parser.add_argument("--ssh-timeout", type=int, default=SSH_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    status = check_dell_ssh(
        args.host,
        tcp_timeout_seconds=args.tcp_timeout,
        ssh_timeout_seconds=args.ssh_timeout,
    )
    print(status.line())
    return 0 if status.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
