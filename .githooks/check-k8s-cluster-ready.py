"""Check whether the two-node Kubernetes rehearsal target is ready."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable


EXPECTED_NODES = ("minthelper01-lenovo-c50-30", "dell-ubuntu-01-optiplex-micro-7010")
REQUIRED_SERVICES = (
    ("xf-app", "backend"),
    ("xf-app", "frontend"),
    ("xf-app", "redis"),
    ("xf-app", "pgbouncer"),
    ("xf-registry", "registry"),
)


KubectlRunner = Callable[[list[str]], str]


@dataclass(frozen=True)
class CheckResult:
    ready: bool
    messages: tuple[str, ...]


def default_runner(args: list[str]) -> str:
    """Run kubectl with a bounded timeout."""
    completed = subprocess.run(
        ["kubectl", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return completed.stdout


def check_cluster(runner: KubectlRunner = default_runner) -> CheckResult:
    """Return readiness messages for the core rehearsal cluster."""
    messages: list[str] = []
    try:
        messages.extend(_node_messages(_json(runner, ["get", "nodes", "-o", "json"])))
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        messages.append(f"FAIL: kubectl could not read cluster nodes: {exc}")
        return CheckResult(ready=False, messages=tuple(messages))
    for namespace, name in REQUIRED_SERVICES:
        messages.extend(_service_messages(runner, namespace, name))
    ready = not any(message.startswith("FAIL:") for message in messages)
    return CheckResult(ready=ready, messages=tuple(messages))


def _json(runner: KubectlRunner, args: list[str]) -> dict:
    return json.loads(runner(args))


def _node_messages(payload: dict) -> list[str]:
    nodes = {item["metadata"]["name"]: item for item in payload.get("items", [])}
    messages: list[str] = []
    for expected in EXPECTED_NODES:
        node = nodes.get(expected)
        if not node:
            messages.append(f"FAIL: missing node {expected}")
            continue
        condition = _ready_condition(node)
        if condition == "True":
            messages.append(f"PASS: node {expected} is Ready")
        else:
            messages.append(f"FAIL: node {expected} is not Ready")
    if len(nodes) != len(EXPECTED_NODES):
        messages.append(f"FAIL: expected 2 nodes, found {len(nodes)}")
    return messages


def _ready_condition(node: dict) -> str:
    for condition in node.get("status", {}).get("conditions", []):
        if condition.get("type") == "Ready":
            return str(condition.get("status", ""))
    return ""


def _service_messages(runner: KubectlRunner, namespace: str, name: str) -> list[str]:
    try:
        runner(["get", "service", name, "-n", namespace, "-o", "name"])
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return [f"FAIL: service {namespace}/{name} is missing or unreachable: {exc}"]
    return [f"PASS: service {namespace}/{name} exists"]


def dry_run_messages() -> tuple[str, ...]:
    """Return the checks that a live readiness run will perform."""
    service_list = ", ".join(f"{namespace}/{name}" for namespace, name in REQUIRED_SERVICES)
    return (
        "PASS: dry run only",
        "Would check nodes: " + ", ".join(EXPECTED_NODES),
        "Would check services: " + service_list,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Kubernetes rehearsal readiness.")
    parser.add_argument("--dry-run", action="store_true", help="Print checks without calling kubectl.")
    args = parser.parse_args(argv)

    result = CheckResult(True, dry_run_messages()) if args.dry_run else check_cluster()
    for message in result.messages:
        print(message)
    print(f"[K8S CLUSTER READY: {'yes' if result.ready else 'no'}]")
    return 0 if result.ready else 1


if __name__ == "__main__":
    sys.exit(main())
