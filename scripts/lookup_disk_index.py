#!/usr/bin/env python3
"""Fast disk-backed lookup for resolved issue lessons."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = REPO_ROOT / "audit" / "resolved_issues_index.jsonl"
DEFAULT_AUDIT_LOG = REPO_ROOT / "audit" / "resolved_issues_lookup_log.jsonl"
DEFAULT_HANDOFF = REPO_ROOT / "AGENT-HANDOFF.md"
_SESSION_KEY = "session_id="


def normalise_path(path: str) -> str:
    return str(path).replace("\\", "/").strip().strip("/")


def load_index(index_path: Path) -> dict[str, list[dict]]:
    if not index_path.exists():
        return {}
    grouped: dict[str, list[dict]] = {}
    with index_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            entry = _decode_line(line)
            if not entry:
                continue
            file_path = normalise_path(entry.get("file_path", ""))
            if file_path:
                grouped.setdefault(file_path, []).append(entry)
    return grouped


def _decode_line(line: str) -> dict | None:
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    return entry if isinstance(entry, dict) else None


def lookup_area(index: dict[str, list[dict]], area: str) -> list[dict]:
    return list(index.get(normalise_path(area), []))


def result_ids(rows: list[dict]) -> list[int]:
    ids: list[int] = []
    for row in rows:
        raw_id = row.get("autoissue_id")
        if isinstance(raw_id, int):
            ids.append(raw_id)
    return ids


def current_task_id(handoff_path: Path) -> str:
    text = _read_text(handoff_path)
    session_id = _latest_session_id(text)
    if session_id:
        return session_id
    today = time.strftime("%Y-%m-%d", time.gmtime())
    return f"fallback-disk-index-{today}"


def _latest_session_id(text: str) -> str:
    found = ""
    for line in text.splitlines():
        if "[TDD PREFLIGHT:" not in line or _SESSION_KEY not in line:
            continue
        found = line.split(_SESSION_KEY, 1)[1].split()[0].strip("]")
    return found


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def append_audit_entry(
    *,
    audit_path: Path,
    file_path: str,
    task_id: str,
    agent: str,
    rows: list[dict],
) -> dict:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "file_path": normalise_path(file_path),
        "lookup_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task_id": task_id,
        "agent": agent,
        "result_count": len(rows),
        "result_ids": result_ids(rows),
    }
    with audit_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


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


def main(argv: list[str] | None = None) -> int:
    try:
        opts = parse_args(list(argv or []))
    except ValueError as exc:
        print(f"lookup_disk_index.py: error: {exc}", file=sys.stderr)
        return 2
    index = load_index(opts.index)
    task_id = current_task_id(opts.handoff)
    for area in opts.area:
        rows = lookup_area(index, area)
        append_audit_entry(
            audit_path=opts.audit_log,
            file_path=area,
            task_id=task_id,
            agent=opts.agent,
            rows=rows,
        )
        _print_result(area, rows)
    return 0


def _print_result(area: str, rows: list[dict]) -> None:
    if not rows:
        print(f"[RESOLVED SEARCH: {normalise_path(area)}: 0 matches]")
        return
    ids = ", ".join(f"#{row_id}" for row_id in result_ids(rows))
    print(f"[RESOLVED SEARCH: {normalise_path(area)}: {len(rows)} prior fix(es)] {ids}")


class _Options:
    def __init__(self) -> None:
        self.area: list[str] = []
        self.index = DEFAULT_INDEX
        self.audit_log = DEFAULT_AUDIT_LOG
        self.handoff = DEFAULT_HANDOFF
        self.agent = "codex"


def _set_area(opts: _Options, value: str) -> None:
    opts.area.append(value)


def _set_index(opts: _Options, value: str) -> None:
    opts.index = Path(value)


def _set_audit_log(opts: _Options, value: str) -> None:
    opts.audit_log = Path(value)


def _set_handoff(opts: _Options, value: str) -> None:
    opts.handoff = Path(value)


def _set_agent(opts: _Options, value: str) -> None:
    opts.agent = value


_VALUE_FLAGS = {
    "--area": _set_area,
    "--index": _set_index,
    "--audit-log": _set_audit_log,
    "--handoff": _set_handoff,
    "--agent": _set_agent,
}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
