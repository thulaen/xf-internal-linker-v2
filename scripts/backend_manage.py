"""Run Django management commands through the live backend runner."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_NAMESPACE = "xf-app"
DEFAULT_TARGET = "deploy/backend"
DEFAULT_TIMEOUT_SECONDS = 180
AUDIT_DIR_ENV = "XF_AUDIT_DIR"
DEFAULT_K8S_AUDIT_DIR = "/tmp/xf-linker-audit"
TRANSPORT_ENV = "XF_BACKEND_MANAGE_TRANSPORT"
NAMESPACE_ENV = "XF_BACKEND_MANAGE_NAMESPACE"
TARGET_ENV = "XF_BACKEND_MANAGE_TARGET"
KUBECTL_ENV = "XF_BACKEND_MANAGE_KUBECTL"
K8S_SSH_HOST_ENV = "XF_BACKEND_MANAGE_K8S_SSH_HOST"
DEFAULT_K8S_SSH_HOST = "mint-wifi"


def build_manage_command(
    args: Sequence[str],
    *,
    transport: str | None = None,
    extra_env: Sequence[str] = (),
) -> list[str]:
    """Build the command that runs ``manage.py`` without local MSI Docker."""
    selected = (transport or os.environ.get(TRANSPORT_ENV) or "k8s").strip().lower()
    if selected == "compose":
        env_args = [part for item in extra_env for part in ("-e", item)]
        return [
            "docker",
            "compose",
            "exec",
            "-T",
            *env_args,
            "backend",
            "python",
            "manage.py",
            *args,
        ]
    if selected not in {"k8s", "kubernetes"}:
        raise ValueError(f"unknown backend command transport: {selected}")
    namespace = os.environ.get(NAMESPACE_ENV, DEFAULT_NAMESPACE)
    target = os.environ.get(TARGET_ENV, DEFAULT_TARGET)
    k8s_env = _kubernetes_extra_env(extra_env)
    env_prefix = ["env", *k8s_env] if k8s_env else []
    kubectl_command = os.environ.get(KUBECTL_ENV, "kubectl")
    command = [
        kubectl_command,
        "-n",
        namespace,
        "exec",
        target,
        "--",
        *env_prefix,
        "python",
        "manage.py",
        *args,
    ]
    if shutil.which(kubectl_command):
        return command
    return ["ssh", os.environ.get(K8S_SSH_HOST_ENV, DEFAULT_K8S_SSH_HOST), shlex.join(command)]


def _kubectl_prefix(kubectl_command: str) -> list[str]:
    if shutil.which(kubectl_command):
        return [kubectl_command]
    return ["ssh", os.environ.get(K8S_SSH_HOST_ENV, DEFAULT_K8S_SSH_HOST), kubectl_command]


def _kubernetes_extra_env(extra_env: Sequence[str]) -> list[str]:
    """Return Kubernetes env entries, including a writable audit folder."""
    values = list(extra_env)
    if not _has_env(values, AUDIT_DIR_ENV):
        values.insert(0, f"{AUDIT_DIR_ENV}={DEFAULT_K8S_AUDIT_DIR}")
    return values


def _has_env(values: Sequence[str], key: str) -> bool:
    return any(value.split("=", 1)[0] == key for value in values)


def run_manage(
    args: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    extra_env: Sequence[str] = (),
) -> int:
    """Run a backend management command and relay its output."""
    try:
        result = subprocess.run(
            build_manage_command(args, extra_env=extra_env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        _print_unreachable("kubectl is not available on MSI and the SSH fallback failed.")
        return 127
    except OSError as exc:
        _print_unreachable(f"system error: {exc}")
        return 127
    except subprocess.TimeoutExpired:
        _print_unreachable(f"command timed out after {timeout} seconds.")
        return 124
    _relay_output(result)
    return result.returncode


def _relay_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def _print_unreachable(detail: str) -> None:
    print(
        "FAIL backend command: the Kubernetes backend is unreachable.\n"
        "WHY: MSI no longer runs the app through local Docker. Normal repo "
        "commands must reach the live backend pod in Kubernetes.\n"
        "UNBLOCK: verify access with `kubectl -n xf-app get pods` or "
        "`ssh mint-wifi kubectl -n xf-app get pods`, then re-run this command.\n"
        f"Detail: {detail}",
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    extra_env, args = split_cli_args(list(sys.argv[1:] if argv is None else argv))
    return run_manage(args, extra_env=extra_env)


def split_cli_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Read optional ``--env KEY=VALUE`` entries before the manage.py command."""
    extra_env: list[str] = []
    remaining = list(argv)
    while remaining[:1] == ["--env"]:
        if len(remaining) < 2 or "=" not in remaining[1]:
            raise SystemExit("FAIL backend command: --env requires KEY=VALUE.")
        extra_env.append(remaining[1])
        remaining = remaining[2:]
    if remaining[:1] == ["--"]:
        remaining = remaining[1:]
    return extra_env, remaining


if __name__ == "__main__":
    raise SystemExit(main())
