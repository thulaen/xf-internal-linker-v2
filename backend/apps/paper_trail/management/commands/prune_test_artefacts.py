"""manage.py prune_test_artefacts — per-prefix cap with LRU eviction."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.core.management.base import BaseCommand


_PREFIX_CAPS_MB = {
    "mull": 200,
    "coverage": 100,
    "mutmut": 100,
    "stryker": 100,
    "fuzz-work": 200,
    "pytest-debug": 50,
}


def _dir_size_mb(path: Path) -> float:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


class Command(BaseCommand):
    help = "Enforce per-prefix size cap with LRU eviction over /tmp artefact dirs."

    def add_arguments(self, parser):
        parser.add_argument("--prefix", required=True,
                            choices=sorted(_PREFIX_CAPS_MB.keys()),
                            help="Artefact prefix to enforce.")
        parser.add_argument("--root", default="/tmp",
                            help="Root directory to scan.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        prefix = opts["prefix"]
        cap_mb = _PREFIX_CAPS_MB[prefix]
        root = Path(opts["root"])
        if not root.is_dir():
            self.stderr.write(
                f"FAIL prune_test_artefacts: root {root} is not a directory.\n"
            )
            raise SystemExit(2)

        candidates = sorted(
            (d for d in root.iterdir() if d.is_dir() and d.name.startswith(prefix + "-")
             or d.is_dir() and d.name == prefix),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            self.stdout.write(
                f"[PRUNE TEST ARTEFACTS: prefix={prefix} cap_mb={cap_mb} "
                f"current_mb=0 evicted=0]"
            )
            return

        total_mb = sum(_dir_size_mb(d) for d in candidates)
        evicted = 0
        if total_mb <= cap_mb:
            self.stdout.write(
                f"[PRUNE TEST ARTEFACTS: prefix={prefix} cap_mb={cap_mb} "
                f"current_mb={total_mb:.1f} evicted=0]"
            )
            return

        # Oldest-first eviction until under cap.
        for d in candidates:
            if total_mb <= cap_mb:
                break
            sz = _dir_size_mb(d)
            if opts["dry_run"]:
                self.stdout.write(f"DRY: would evict {d} ({sz:.1f} MB)")
            else:
                try:
                    shutil.rmtree(d)
                except OSError as exc:
                    self.stderr.write(f"WARN: failed to remove {d}: {exc}\n")
                    continue
            total_mb -= sz
            evicted += 1

        self.stdout.write(
            f"[PRUNE TEST ARTEFACTS: prefix={prefix} cap_mb={cap_mb} "
            f"current_mb={total_mb:.1f} evicted={evicted}]"
        )
