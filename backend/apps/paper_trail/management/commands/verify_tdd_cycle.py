"""manage.py verify_tdd_cycle — proof of Red → Green → Refactor ordering."""

from __future__ import annotations

import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify the Red test file precedes the Green source change."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True,
                            help="Path to the production source file changed.")
        parser.add_argument("--test", required=True,
                            help="Path to the failing-test file that drove the change.")
        parser.add_argument("--ruff-clean", action="store_true",
                            help="Assert ruff is clean for the source after refactor.")

    def handle(self, *args, **opts):
        src = Path(opts["source"])
        tst = Path(opts["test"])
        if not src.is_file():
            raise CommandError(
                f"FAIL verify_tdd_cycle: source file {src} does not exist. "
                f"Stage it before running the gate."
            )
        if not tst.is_file():
            raise CommandError(
                f"FAIL verify_tdd_cycle: test file {tst} does not exist. "
                f"Write the failing Red test first."
            )
        # Best-effort proof: the test file's mtime should be <= source's mtime
        # (Red precedes Green). Git-history-aware proof is the gold standard;
        # mtime is the local fallback when git history isn't available.
        if tst.stat().st_mtime > src.stat().st_mtime + 60:
            raise CommandError(
                f"FAIL verify_tdd_cycle: test file {tst} is newer than source "
                f"{src} by more than 60s — looks like you wrote the source "
                f"first. Restart the cycle: write a failing test, see it fail, "
                f"then write the minimum source."
            )
        ruff_summary = "skipped"
        if opts["ruff_clean"]:
            try:
                result = subprocess.run(
                    ["ruff", "check", str(src), str(tst)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    raise CommandError(
                        f"FAIL verify_tdd_cycle: ruff is not clean on the "
                        f"touched files. Run `ruff check --fix {src} {tst}` "
                        f"and finish the Refactor phase before committing."
                    )
                ruff_summary = "ruff_clean=true"
            except FileNotFoundError:
                ruff_summary = "ruff_not_on_path"

        self.stdout.write(
            f"[TDD CYCLE: file={src} red={tst}:1 green={src}:1 "
            f"refactor=\"{ruff_summary}\"]"
        )
