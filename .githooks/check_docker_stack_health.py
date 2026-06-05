from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "docker-stack-health.json"
TIMEOUT_SECONDS = 30


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG
    return json.loads(config_path.read_text(encoding="utf-8"))


def check_target(target: dict[str, Any]) -> list[str]:
    if target.get("enabled") is False:
        return []
    config_error = _validate_target(target)
    if config_error:
        return [config_error]
    containers = tuple(str(item["name"]) for item in target.get("containers", ()))
    if not containers:
        return [f"{target['name']}: no required containers are listed"]
    completed = _inspect_target(target, containers)
    if completed.returncode != 0:
        detail = _trim(completed.stderr or completed.stdout or "no output")
        return [f"{target['name']}: Docker inspect failed: {detail}"]
    try:
        records = _parse_inspect_output(completed.stdout)
    except ValueError as exc:
        return [f"{target['name']}: unreadable Docker inspect output: {_trim(exc)}"]
    failures: list[str] = []
    for expected in target.get("containers", ()):
        name = str(expected["name"])
        record = records.get(name)
        if record is None:
            failures.append(f"{target['name']}:{name}: missing from Docker inspect")
            continue
        state = record.get("State") or {}
        status = str(state.get("Status") or "")
        if status != "running":
            failures.append(f"{target['name']}:{name}: status={status!r}, expected 'running'")
            continue
        expected_health = expected.get("health")
        if expected_health:
            health = str((state.get("Health") or {}).get("Status") or "")
            if health != expected_health:
                failures.append(
                    f"{target['name']}:{name}: health={health!r}, expected {expected_health!r}"
                )
    return failures


def _validate_target(target: dict[str, Any]) -> str:
    name = str(target.get("name") or "<unnamed>")
    kind = target.get("kind")
    if not target.get("name"):
        return "<unnamed>: missing required config field 'name'"
    if kind == "docker-context" and not target.get("context"):
        return f"{name}: missing required config field 'context'"
    if kind == "ssh" and not target.get("host"):
        return f"{name}: missing required config field 'host'"
    if kind not in {"docker-context", "ssh"}:
        return f"{name}: unknown Docker stack target kind {kind!r}"
    return ""


def _inspect_target(target: dict[str, Any], containers: Sequence[str]) -> subprocess.CompletedProcess[str]:
    command = _inspect_command(target, containers)
    try:
        return subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=_trim(exc.stdout),
            stderr=_trim(exc.stderr) or f"timed out after {TIMEOUT_SECONDS}s",
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, returncode=127, stdout="", stderr=str(exc))


def _inspect_command(target: dict[str, Any], containers: Sequence[str]) -> list[str]:
    format_arg = "{{json .}}"
    kind = target.get("kind")
    if kind == "docker-context":
        return [
            "docker",
            "--context",
            str(target["context"]),
            "inspect",
            "--format",
            format_arg,
            *containers,
        ]
    if kind == "ssh":
        return [
            "ssh",
            str(target["host"]),
            "docker",
            "inspect",
            "--format",
            f"'{format_arg}'",
            *containers,
        ]
    raise ValueError(f"Unknown Docker stack target kind: {kind!r}")


def _parse_inspect_output(output: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(output.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: {exc.msg}: {text[:160]}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number}: expected object, got {type(payload).__name__}")
        name = str(payload.get("Name") or "").lstrip("/")
        if name:
            records[name] = payload
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    failures: list[str] = []
    for target in config.get("targets", ()):
        failures.extend(check_target(target))
    if not failures:
        return 0
    sys.stderr.write(
        "FAIL check-docker-stack-health: required Docker containers are not up.\n"
        "WHY: a commit is not allowed while the Windows, Mint, or configured helper-PC Docker stack is down, because broken runtime services hide real test, scan, profile, and app failures.\n"
        "DOWN:\n"
        + "\n".join(f"  {failure}" for failure in failures)
        + "\nUNBLOCK: start or repair the named machine's Docker stack, then rerun the commit. For Mint quality services, use `powershell -ExecutionPolicy Bypass -File scripts/check-mint-quality-tools.ps1 -Repair -SkipHaskell`.\n"
    )
    return 2


def _trim(value: object, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[-limit:]


if __name__ == "__main__":
    sys.exit(main())
