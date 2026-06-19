#!/usr/bin/env python3
"""Content-hash cache so unchanged files skip repeat quality runs.

Only PASSING results are recorded. A row means "this exact tool ran over
this exact content with this exact tool config and passed", so the same
content does not need to run again. Failures are never cached, corrupt
cache lines are ignored, and deleting the cache file is always safe —
the cache can only cause extra work, never a skipped check.

Storage: ``audit/quality_cache.jsonl`` (gitignored via ``audit/*.jsonl``),
one JSON object per line: ``{"key": ..., "tool": ..., "ts": ...}``.
Bypass: ``XF_QUALITY_CACHE=0`` disables both lookups and writes.

CLI for shell callers (mutation pairs)::

    python scripts/quality_cache.py filter-pairs --tool mutmut --pairs-file F
    python scripts/quality_cache.py record-pairs --tool mutmut --pairs-file F

where each line of F is ``<source-path>\t<test-path>``. ``filter-pairs``
prints the lines that still need a run; ``record-pairs`` stores passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

_SCHEMA = "v1"
_TTL_SECONDS = 14 * 24 * 3600
_MAX_ROWS = 5000
_CONFIG_FILES = (
    "backend/mypy.ini",
    "backend/pytest.ini",
    "backend/requirements.txt",
    "config/mutation-routing.json",
    "tools/elcv/gate.py",
    "tools/elcv/gate-baseline.json",
    "tools/elcv/uso-index.json",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def config_fingerprint(root: Path) -> str:
    """Hash the tool configs; any config change invalidates all rows."""
    digest = hashlib.sha256()
    for rel in _CONFIG_FILES:
        path = root / rel
        digest.update(rel.encode("utf-8"))
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()


def cache_enabled() -> bool:
    return os.environ.get("XF_QUALITY_CACHE", "1") != "0"


class QualityCache:
    """JSONL-backed pass cache keyed by tool + config + content hashes."""

    def __init__(self, root: Path, now: float | None = None) -> None:
        self.root = Path(root)
        self.path = self.root / "audit" / "quality_cache.jsonl"
        self.now = time.time() if now is None else now
        self.fingerprint = config_fingerprint(self.root)
        self._rows: dict[str, dict[str, object]] = self._load()

    def _load(self) -> dict[str, dict[str, object]]:
        rows: dict[str, dict[str, object]] = {}
        if not cache_enabled() or not self.path.exists():
            return rows
        text = self.path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            try:
                row = json.loads(line)
                key, ts = str(row["key"]), float(row["ts"])
            except (ValueError, KeyError, TypeError):
                continue
            if self.now - ts <= _TTL_SECONDS:
                row["ts"] = ts
                rows[key] = row
        return rows

    def key_for(self, tool: str, subject_hash: str) -> str:
        return _sha256_text("|".join((_SCHEMA, tool, self.fingerprint, subject_hash)))

    def subject_hash_for_files(self, paths: list[Path]) -> str:
        parts = sorted(f"{Path(p).as_posix()}:{_file_hash(Path(p))}" for p in paths)
        return _sha256_text("|".join(parts))

    def subject_hash_for_gate(self, paths: list[Path], command_text: str) -> str:
        """Hash a gate command plus the scoped files it checked."""
        gate_paths = list(paths)
        for token in command_text.split():
            candidate = self.root / token
            if candidate.exists() and candidate.is_file():
                gate_paths.append(candidate)
        files_hash = self.subject_hash_for_files(gate_paths)
        return _sha256_text(f"gate|{command_text}|{files_hash}")

    def has_pass(
        self,
        tool: str,
        subject_hash: str,
        max_age_seconds: int | None = None,
    ) -> bool:
        if not cache_enabled():
            return False
        row = self._rows.get(self.key_for(tool, subject_hash))
        if row is None:
            return False
        if max_age_seconds is None:
            return True
        return self.now - float(row["ts"]) <= max_age_seconds

    def filter(
        self, tool: str, subjects: dict[str, str]
    ) -> tuple[list[str], list[str]]:
        """Split subject names into (to_run, skipped) by cached passes."""
        to_run: list[str] = []
        skipped: list[str] = []
        for name, subject_hash in subjects.items():
            bucket = skipped if self.has_pass(tool, subject_hash) else to_run
            bucket.append(name)
        return sorted(to_run), sorted(skipped)

    def record(self, tool: str, subject_hashes: list[str]) -> None:
        """Store passes only; callers must never record failures."""
        if not cache_enabled() or not subject_hashes:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for subject_hash in subject_hashes:
                row = {"key": self.key_for(tool, subject_hash), "tool": tool,
                       "ts": self.now}
                self._rows[str(row["key"])] = row
                handle.write(json.dumps(row) + "\n")
        self._compact_if_needed()

    def _compact_if_needed(self) -> None:
        try:
            with self.path.open(encoding="utf-8") as handle:
                line_count = sum(1 for _ in handle)
        except OSError:
            return
        if line_count <= _MAX_ROWS:
            return
        live = "".join(json.dumps(row) + "\n" for row in self._rows.values())
        self.path.write_text(live, encoding="utf-8")


def _read_pairs(pairs_file: Path) -> list[tuple[str, list[Path]]]:
    pairs: list[tuple[str, list[Path]]] = []
    for line in pairs_file.read_text(encoding="utf-8").splitlines():
        fields = [part for part in line.replace("\t", " ").split() if part]
        if fields:
            pairs.append((line, [Path(part) for part in fields]))
    return pairs


def _paths_from_env(root: Path, env_name: str | None) -> list[Path]:
    if not env_name:
        return []
    value = os.environ.get(env_name, "")
    paths: list[Path] = []
    for raw in value.splitlines():
        rel = raw.strip()
        if rel:
            paths.append(root / rel)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("filter-pairs", "record-pairs", "check-gate", "record-gate"),
    )
    parser.add_argument("--tool", required=True)
    parser.add_argument("--pairs-file")
    parser.add_argument("--paths-env")
    parser.add_argument("--command-text", default="")
    parser.add_argument("--ttl-seconds", type=int)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    cache = QualityCache(Path(args.root).resolve())
    if args.command in {"check-gate", "record-gate"}:
        subject = cache.subject_hash_for_gate(
            _paths_from_env(cache.root, args.paths_env),
            args.command_text,
        )
        if args.command == "check-gate":
            if cache.has_pass(args.tool, subject, args.ttl_seconds):
                print(f"quality-cache:gate-pass-cached {args.tool}")
                return 0
            return 1
        cache.record(args.tool, [subject])
        return 0

    if not args.pairs_file:
        parser.error("--pairs-file is required for pair cache commands")
    pairs = _read_pairs(Path(args.pairs_file))
    for raw_line, paths in pairs:
        subject = cache.subject_hash_for_files(paths)
        if args.command == "filter-pairs":
            if not cache.has_pass(args.tool, subject):
                print(raw_line)
        else:
            cache.record(args.tool, [subject])
    return 0


if __name__ == "__main__":
    sys.exit(main())
