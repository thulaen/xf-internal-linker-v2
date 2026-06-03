"""Build and read cached session-start payloads."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from django.conf import settings
from django.core.management import call_command

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_TTL = timedelta(minutes=5)
PAYLOAD_VERSION = 1


class PayloadError(RuntimeError):
    """Raised when the cached startup payload cannot be trusted."""


@dataclass(frozen=True)
class StartupPayload:
    """One cached startup payload served by the Go helper."""

    version: int
    generated_at: datetime
    expires_at: datetime
    markers: list[str]
    autoissues: list[str]
    body: str


def default_payload_path() -> Path:
    """Return the shared cache file path used by backend and startupd."""
    repo_root = Path(os.environ.get("REPO_ROOT") or "/repo")
    if not repo_root.exists():
        repo_root = Path(settings.BASE_DIR).parent
    return repo_root / "audit" / "session_start_payload.jsonl"


def extract_marker_lines(text: str) -> list[str]:
    """Return protocol marker lines from command output."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("[") and "]" in line
    ]


def extract_autoissue_lines(text: str) -> list[str]:
    """Return the registry marker and issue rows from startup output."""
    lines: list[str] = []
    inside_registry = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[REGISTRY READ:"):
            inside_registry = True
            lines.append(stripped)
            continue
        if inside_registry and stripped.startswith("["):
            break
        if inside_registry and stripped.startswith("#"):
            lines.append(stripped)
    return lines


def build_payload(
    *,
    command_runner: Callable[[str, list[str]], str] | None = None,
    handoff_reader: Callable[[], str] | None = None,
    now: Callable[[], datetime] | None = None,
) -> StartupPayload:
    """Build a payload by running the slow startup reads once."""
    run = command_runner or _run_management_command
    read_handoff = handoff_reader or _read_handoff
    current_time = _coerce_utc((now or _utc_now)())

    sections = [_handoff_marker(read_handoff())]
    sections.extend(
        [
            run("print_open_issues", []),
            run("print_open_paper_trail", []),
            run("print_open_snapshots", []),
            run("print_failed_github_actions", ["--since-handoff"]),
            _sticky_marker(run("read_sticky", ["--id", "1", "--print-sha-only"]), current_time),
            run("preflight_tdd", []),
        ]
    )
    body = "\n".join(part.strip() for part in sections if part.strip())
    return StartupPayload(
        version=PAYLOAD_VERSION,
        generated_at=current_time,
        expires_at=current_time + DEFAULT_TTL,
        markers=extract_marker_lines(body),
        autoissues=extract_autoissue_lines(body),
        body=body,
    )


def write_payload(path: Path, payload: StartupPayload) -> None:
    """Atomically replace the one-line JSON cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _payload_to_json(payload) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
    temp_path.replace(path)


def read_helper_payload(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    now: Callable[[], datetime] | None = None,
) -> StartupPayload:
    """Read and validate a cached payload from startupd."""
    try:
        with urlopen(url, timeout=timeout_seconds) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise PayloadError(f"cached startup payload unavailable: {exc}") from exc
    payload = _payload_from_json(raw)
    current_time = _coerce_utc((now or _utc_now)())
    if payload.expires_at <= current_time:
        raise PayloadError("cached startup payload is stale")
    return payload


def _run_management_command(name: str, args: list[str]) -> str:
    out = StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


def _read_handoff() -> str:
    path = Path(os.environ.get("REPO_ROOT") or "/repo") / "AGENT-HANDOFF.md"
    if not path.exists():
        path = Path(settings.BASE_DIR).parent / "AGENT-HANDOFF.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PayloadError(f"handoff file could not be read: {exc}") from exc


def _handoff_marker(text: str) -> str:
    first_line = next((line for line in text.splitlines() if line.startswith("# ")), "")
    parts = [part.strip() for part in first_line.removeprefix("# ").split(" - ", 2)]
    if len(parts) != 3:
        return "[HANDOFF READ: unknown by unknown — latest handoff heading could not be parsed]"
    return f"[HANDOFF READ: {parts[0]} by {parts[1]} — {parts[2]}]"


def _sticky_marker(sha_output: str, timestamp: datetime) -> str:
    sha = sha_output.strip().splitlines()[-1].strip()
    stamp = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    agent = (os.environ.get("XF_AGENT_NAME") or "claude").strip() or "claude"
    return f"[STICKY 1 READ: timestamp={stamp} sha256={sha} agent={agent}]"


def _payload_to_json(payload: StartupPayload) -> str:
    data = asdict(payload)
    data["generated_at"] = _format_dt(payload.generated_at)
    data["expires_at"] = _format_dt(payload.expires_at)
    return json.dumps(data, sort_keys=True)


def _payload_from_json(raw: str) -> StartupPayload:
    try:
        data = json.loads(raw)
        return StartupPayload(
            version=int(data["version"]),
            generated_at=_parse_dt(data["generated_at"]),
            expires_at=_parse_dt(data["expires_at"]),
            markers=list(data["markers"]),
            autoissues=list(data.get("autoissues", [])),
            body=str(data["body"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PayloadError("cached startup payload is malformed") from exc


def _format_dt(value: datetime) -> str:
    return _coerce_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
