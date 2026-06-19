"""Unit tests for the Dell SSH preflight helper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import dell_ssh_preflight as preflight


def _run_for_banner_timeout(cmd, **kwargs):
    if cmd[:2] == ["ssh", "-G"]:
        return SimpleNamespace(stdout="hostname 192.168.0.163\nport 22\n")
    return SimpleNamespace(
        returncode=255,
        stdout="",
        stderr=(
            "Connection timed out during banner exchange\r\n"
            "Connection to 192.168.0.163 port 22 timed out\r\n"
        ),
    )


def test_tcp_open_plus_banner_timeout_is_reported_clearly(monkeypatch):
    monkeypatch.setattr(preflight.subprocess, "run", _run_for_banner_timeout)
    monkeypatch.setattr(
        preflight.socket,
        "create_connection",
        lambda address, timeout: _FakeSocket(),
    )

    status = preflight.check_dell_ssh("dell")

    assert status.label == "Dell SSH banner timeout"
    assert not status.ok
    assert status.address == "192.168.0.163"
    assert "Restart Dell's SSH service" in status.next_action


def test_tcp_closed_reports_power_wifi_or_ip_next_action(monkeypatch):
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="hostname dell\nport 22\n"),
    )

    def fail_tcp(address, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(preflight.socket, "create_connection", fail_tcp)

    status = preflight.check_dell_ssh("dell")

    assert status.label == "Dell port closed"
    assert "power" in status.next_action.lower()


def test_login_failed_reports_ssh_config_and_key_next_action(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["ssh", "-G"]:
            return SimpleNamespace(stdout="hostname 192.168.0.163\nport 22\n")
        return SimpleNamespace(
            returncode=255,
            stdout="",
            stderr="Permission denied (publickey).\n",
        )

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    monkeypatch.setattr(
        preflight.socket,
        "create_connection",
        lambda address, timeout: _FakeSocket(),
    )

    status = preflight.check_dell_ssh("dell")

    assert status.label == "Dell login failed"
    assert "~/.ssh/config" in status.next_action


def test_require_ready_raises_with_banner_timeout(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "check_dell_ssh", lambda host: preflight.DellSshStatus(
        "Dell SSH banner timeout",
        host,
        "192.168.0.163",
        22,
        False,
        "Connection timed out during banner exchange",
        "Restart Dell's SSH service or reboot Dell, then retry.",
    ))

    with pytest.raises(SystemExit) as excinfo:
        preflight.require_dell_ssh_ready("dell")

    assert excinfo.value.code == 2
    assert "Dell SSH banner timeout" in capsys.readouterr().err


def test_default_ssh_timeout_allows_slow_dell_banner(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[:2] == ["ssh", "-G"]:
            return SimpleNamespace(stdout="hostname 192.168.0.163\nport 22\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    monkeypatch.setattr(
        preflight.socket,
        "create_connection",
        lambda address, timeout: _FakeSocket(),
    )

    status = preflight.check_dell_ssh("dell")

    assert status.ok
    assert calls[1][1]["timeout"] == preflight.SSH_TIMEOUT_SECONDS + 2
    assert f"ConnectTimeout={preflight.SSH_TIMEOUT_SECONDS}" in calls[1][0]
    assert "-tt" in calls[1][0]


def test_proxyjump_skips_direct_tcp_check(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["ssh", "-G"]:
            return SimpleNamespace(
                stdout="hostname 10.10.10.92\nport 22\nproxyjump mint-wifi\n"
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fail_if_called(address, timeout):
        raise AssertionError("direct TCP check should not run with ProxyJump")

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    monkeypatch.setattr(preflight.socket, "create_connection", fail_if_called)

    status = preflight.check_dell_ssh("dell")

    assert status.ok
    assert status.address == "10.10.10.92"


def test_proxycommand_skips_direct_tcp_check(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["ssh", "-G"]:
            return SimpleNamespace(
                stdout=(
                    "hostname 10.10.10.92\n"
                    "port 22\n"
                    "proxycommand C:\\Windows\\System32\\OpenSSH\\ssh.exe -W %h:%p mint-wifi\n"
                )
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fail_if_called(address, timeout):
        raise AssertionError("direct TCP check should not run with ProxyCommand")

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    monkeypatch.setattr(preflight.socket, "create_connection", fail_if_called)

    status = preflight.check_dell_ssh("dell")

    assert status.ok
    assert status.address == "10.10.10.92"


def test_broken_proxycommand_uses_explicit_jump_host_first(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["ssh", "-G"]:
            return SimpleNamespace(
                stdout=(
                    "hostname 10.10.10.92\n"
                    "user dell-ubuntu-01\n"
                    "port 22\n"
                    "identityfile ~/.ssh/dell_xf\n"
                    "proxycommand exec C:\\Windows\\System32\\OpenSSH\\ssh.exe -W %h:%p mint-wifi\n"
                )
            )
        if any(part.startswith("ProxyCommand=ssh") for part in cmd):
            return SimpleNamespace(returncode=0, stdout="", stderr="Connection closed.\n")
        return SimpleNamespace(
            returncode=255,
            stdout="",
            stderr="exec : The term 'exec' is not recognized.\n",
        )

    def fail_if_called(address, timeout):
        raise AssertionError("direct TCP check should not run with ProxyCommand")

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    monkeypatch.setattr(preflight.socket, "create_connection", fail_if_called)

    status = preflight.check_dell_ssh("dell")

    assert status.ok
    assert len(calls) == 2
    fallback = calls[-1]
    proxy_option = next(part for part in fallback if part.startswith("ProxyCommand=ssh"))
    assert " -W %h:%p mint-wifi" in proxy_option
    assert "exec " not in proxy_option
    assert "dell-ubuntu-01@10.10.10.92" in fallback
    assert any(part.replace("\\", "/").endswith(".ssh/dell_xf") for part in fallback)


def test_ssh_base_command_uses_explicit_jump_host(monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(
            stdout=(
                "hostname 10.10.10.92\n"
                "user dell-ubuntu-01\n"
                "port 22\n"
                "identityfile ~/.ssh/dell_xf\n"
                "proxycommand exec C:\\Windows\\System32\\OpenSSH\\ssh.exe -W %h:%p mint-wifi\n"
            )
        )

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)

    command = preflight.ssh_base_command("dell")

    proxy_option = next(part for part in command if part.startswith("ProxyCommand=ssh"))
    assert " -W %h:%p mint-wifi" in proxy_option
    assert "exec " not in proxy_option
    assert any(part.replace("\\", "/").endswith(".ssh/dell_xf") for part in command)
    assert command[-1] == "dell-ubuntu-01@10.10.10.92"


def test_windows_proxy_shell_prefers_git_bash(monkeypatch, tmp_path):
    bash = tmp_path / "bash.exe"
    bash.write_text("", encoding="utf-8")
    monkeypatch.setattr(preflight.os, "name", "nt")
    monkeypatch.setattr(preflight, "WINDOWS_PROXY_SHELL", bash)
    monkeypatch.setenv("SHELL", "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")

    preflight._ensure_windows_proxy_shell()

    assert preflight.os.environ["SHELL"] == str(bash)


class _FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
