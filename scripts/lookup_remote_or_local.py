#!/usr/bin/env python3
"""HTTP-first resolved issue lookup with disk fallback."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, TextIO

from lookup_disk_index import current_task_id, normalise_path

DEFAULT_URL = "http://localhost:8000/api/internal/audit/lookup/"


def parse_args(argv: list[str]) -> "_Options":
    opts = _Options()
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag not in _VALUE_FLAGS or index + 1 >= len(argv):
            raise ValueError(f"missing value for {flag}")
        value = argv[index + 1]
        _VALUE_FLAGS[flag](opts, value)
        index += 2
    if not opts.area:
        raise ValueError("the following arguments are required: --area")
    return opts


def main(
    argv: list[str] | None = None,
    *,
    post_json: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
    run_local: Callable[[list[str]], int] | None = None,
    stdout: TextIO = sys.stdout,
) -> int:
    raw_args = list(argv or [])
    try:
        opts = parse_args(raw_args)
    except ValueError as exc:
        print(f"lookup_remote_or_local.py: error: {exc}", file=sys.stderr)
        return 2
    poster = post_json or _post_json
    fallback = run_local or _run_disk_fallback
    payload = {
        "file_paths": opts.area,
        "task_id": current_task_id(opts.handoff),
        "agent": opts.agent,
    }
    try:
        response = poster(opts.url, payload, opts.timeout)
    except (OSError, urllib.error.URLError, ValueError):
        return fallback(_disk_fallback_args(raw_args))
    _print_response(response, stdout)
    return 0


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status < 200 or response.status >= 300:
            raise urllib.error.URLError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _run_disk_fallback(args: list[str]) -> int:
    script = Path(__file__).resolve().with_name("lookup_disk_index.py")
    return subprocess.call([sys.executable, str(script), *args])


def _disk_fallback_args(args: list[str]) -> list[str]:
    cleaned: list[str] = []
    index = 0
    while index < len(args):
        flag = args[index]
        if flag in {"--url", "--timeout"}:
            index += 2
            continue
        cleaned.append(flag)
        if flag in _VALUE_FLAGS and index + 1 < len(args):
            cleaned.append(args[index + 1])
            index += 2
            continue
        index += 1
    return cleaned


def _print_response(response: dict[str, Any], stdout: TextIO) -> None:
    paths = response.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("remote response missing paths object")
    for file_path, payload in paths.items():
        if not isinstance(payload, dict):
            continue
        count = int(payload.get("result_count") or 0)
        ids = payload.get("result_ids") or []
        area = normalise_path(str(file_path))
        if count == 0:
            print(f"[RESOLVED SEARCH: {area}: 0 matches]", file=stdout)
            continue
        rendered_ids = ", ".join(f"#{issue_id}" for issue_id in ids)
        print(
            f"[RESOLVED SEARCH: {area}: {count} prior fix(es)] {rendered_ids}",
            file=stdout,
        )


class _Options:
    def __init__(self) -> None:
        self.area: list[str] = []
        self.handoff = Path(__file__).resolve().parent.parent / "AGENT-HANDOFF.md"
        self.agent = "codex"
        self.url = DEFAULT_URL
        self.timeout = 1.0


def _set_area(opts: _Options, value: str) -> None:
    opts.area.append(value)


def _set_handoff(opts: _Options, value: str) -> None:
    opts.handoff = Path(value)


def _set_agent(opts: _Options, value: str) -> None:
    opts.agent = value


def _set_url(opts: _Options, value: str) -> None:
    opts.url = value


def _set_timeout(opts: _Options, value: str) -> None:
    opts.timeout = float(value)


_VALUE_FLAGS = {
    "--area": _set_area,
    "--handoff": _set_handoff,
    "--agent": _set_agent,
    "--url": _set_url,
    "--timeout": _set_timeout,
}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
