"""Diagnose why the KUBE PLAN cluster readiness check cannot reach Kubernetes."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse


DEFAULT_TIMEOUT_SECONDS = 20
NODE_TIMEOUT_SECONDS = 60


CommandRunner = Callable[[list[str], int], subprocess.CompletedProcess[str]]
TcpChecker = Callable[[str, int, int], None]


@dataclass(frozen=True)
class Probe:
    label: str
    args: tuple[str, ...]
    timeout: int
    failure_hint: str


@dataclass(frozen=True)
class ProbeResult:
    label: str
    ok: bool
    message: str
    detail: str = ""


PROBES = (
    Probe(
        label="active Kubernetes context",
        args=("kubectl", "config", "current-context"),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        failure_hint="kubectl has no active context. Select the KUBE PLAN context first.",
    ),
    Probe(
        label="Kubernetes API server address",
        args=(
            "kubectl",
            "config",
            "view",
            "--minify",
            "-o",
            "jsonpath={.clusters[0].cluster.server}",
        ),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        failure_hint="kubectl cannot read the API server address from the active context.",
    ),
    Probe(
        label="Kubernetes API health",
        args=("kubectl", "cluster-info", "--request-timeout=20s"),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        failure_hint="the Kubernetes API server is not reachable from MSI.",
    ),
    Probe(
        label="node list",
        args=("kubectl", "get", "nodes", "-o", "wide", "--request-timeout=60s"),
        timeout=NODE_TIMEOUT_SECONDS,
        failure_hint="kubectl cannot list nodes. Check the network route, API server, and credentials.",
    ),
)


def default_runner(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output and a bounded timeout."""
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def default_tcp_checker(host: str, port: int, timeout: int) -> None:
    """Check whether a TCP port accepts a connection."""
    with socket.create_connection((host, port), timeout=timeout):
        return


def run_diagnostics(
    runner: CommandRunner = default_runner,
    tcp_checker: TcpChecker = default_tcp_checker,
) -> tuple[ProbeResult, ...]:
    """Run Kubernetes access probes and return plain-English results."""
    results: list[ProbeResult] = []
    for probe in PROBES:
        result = _run_probe(probe, runner)
        results.append(result)
        if result.ok and probe.label == "Kubernetes API server address":
            results.append(_tcp_probe(result.detail, tcp_checker))
    return tuple(results)


def _run_probe(probe: Probe, runner: CommandRunner) -> ProbeResult:
    try:
        completed = runner(list(probe.args), probe.timeout)
    except FileNotFoundError:
        return ProbeResult(
            probe.label,
            False,
            f"FAIL: {probe.label}: kubectl is not installed or is not on PATH.",
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(
            probe.label,
            False,
            f"FAIL: {probe.label}: timed out after {probe.timeout} seconds. {probe.failure_hint}",
        )

    output = _first_line(completed.stdout) or _first_line(completed.stderr)
    if completed.returncode == 0:
        detail = f": {output}" if output else ""
        return ProbeResult(probe.label, True, f"PASS: {probe.label}{detail}", output)
    detail = f" Output: {output}" if output else ""
    return ProbeResult(
        probe.label,
        False,
        f"FAIL: {probe.label}: command exited with code {completed.returncode}.{detail} "
        f"{probe.failure_hint}",
    )


def _tcp_probe(server_url: str, tcp_checker: TcpChecker) -> ProbeResult:
    parsed = urlparse(server_url)
    host = parsed.hostname
    port = parsed.port or 443
    if not host:
        return ProbeResult(
            "Kubernetes API TCP port",
            False,
            f"FAIL: Kubernetes API TCP port: could not parse API server address {server_url}.",
        )
    try:
        tcp_checker(host, port, DEFAULT_TIMEOUT_SECONDS)
    except OSError as exc:
        return ProbeResult(
            "Kubernetes API TCP port",
            False,
            f"FAIL: Kubernetes API TCP port: {host}:{port} did not accept a connection. {exc}",
        )
    return ProbeResult(
        "Kubernetes API TCP port",
        True,
        f"PASS: Kubernetes API TCP port: {host}:{port} accepts connections",
    )


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose Kubernetes access for KUBE PLAN.")
    parser.add_argument("--dry-run", action="store_true", help="Print the checks without running kubectl.")
    args = parser.parse_args(argv)

    if args.dry_run:
        for probe in PROBES:
            print("Would run: " + " ".join(probe.args))
        print("[K8S ACCESS DIAGNOSIS: dry-run]")
        return 0

    results = run_diagnostics()
    for result in results:
        print(result.message)
    ok = all(result.ok for result in results)
    print(f"[K8S ACCESS DIAGNOSIS: {'pass' if ok else 'fail'}]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
