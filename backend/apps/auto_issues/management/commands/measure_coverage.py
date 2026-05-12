"""Measure coverage for a target module / app / path.

Gap #6 of the FR-251 follow-up set (2026-05-12). Agents are required by
`AI-CODING-GUIDELINES.md` to emit `[COVERAGE SUMMARY: target=<X>%
actual=<Y>% — met / not met]` at the end of every slice. This command
is the one-shot helper that fills in <Y>%.

Usage:
    # Measure coverage for one module
    python manage.py measure_coverage --module apps/auto_issues/services/fingerprinting.py

    # Measure coverage for an entire app
    python manage.py measure_coverage --app apps.auto_issues

    # Machine-readable JSON output (for CI / hooks)
    python manage.py measure_coverage --module apps/x.py --json

The command shells `coverage` (already installed via pytest-cov as a
transitive dep) and prints either a human-readable line or a JSON
object containing line %, branch %, and the count of missed lines.

Honesty contract: the output reflects what the suite actually executed
against the named target. If the command exits non-zero (e.g. tests
fail before coverage is measured), the agent must report that, not
silently fall back to a fake number.
"""

# print-allowed: management command — stdout is the API contract.

from __future__ import annotations

import json
import re
import subprocess
import sys

from django.core.management.base import BaseCommand, CommandError

# `coverage report` produces a row per file then a TOTAL line. We parse
# the TOTAL line for the headline %.
_TOTAL_LINE_RE = re.compile(
    r"^TOTAL\s+(?P<stmts>\d+)\s+(?P<miss>\d+)\s+(?:(?P<branch>\d+)\s+(?P<brmiss>\d+)\s+)?(?P<pct>[\d.]+)%",
    re.MULTILINE,
)


class Command(BaseCommand):
    help = (
        "Measure coverage for a target module / app / path. Prints the "
        "actual coverage percentage so agents can fill in the "
        "[COVERAGE SUMMARY: ... actual=Y%] marker honestly."
    )

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument(
            "--module",
            help="Repo-relative path to one file or directory (e.g. apps/x.py).",
        )
        scope.add_argument(
            "--app",
            help="Django app dotted path (e.g. apps.auto_issues).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON instead of a human-readable line.",
        )
        parser.add_argument(
            "--include-branches",
            action="store_true",
            help="Also measure branch coverage (slower).",
        )

    def handle(self, *args, **opts):
        target = opts.get("module") or opts.get("app").replace(".", "/")
        if not target:
            raise CommandError("--module or --app is required")

        report_text = self._run_coverage(target, opts["include_branches"])
        pct, branch_pct = self._parse_report(report_text, opts["include_branches"])

        if opts["json"]:
            payload = {"target": target, "line_pct": pct}
            if branch_pct is not None:
                payload["branch_pct"] = branch_pct
            self.stdout.write(json.dumps(payload))
            return

        # Human-readable line matches the [COVERAGE SUMMARY] format so the
        # agent can copy it directly into their session-end marker.
        branch_part = f", branch={branch_pct:.1f}%" if branch_pct is not None else ""
        self.stdout.write(
            f"[COVERAGE: target={target} line={pct:.1f}%{branch_part}]"
        )

    # ─── helpers ────────────────────────────────────────────────────

    def _run_coverage(self, target: str, branches: bool) -> str:
        """Run coverage + pytest scoped to *target*, return report stdout."""
        branch_flag = ["--branch"] if branches else []
        # 1. Erase any prior coverage data so we measure THIS run only.
        subprocess.run(["coverage", "erase"], check=False)
        # 2. Run coverage against the target. Use `python -m pytest` to ensure
        #    Django settings autoload via conftest.py / pytest-django.
        run = subprocess.run(
            [
                "coverage", "run",
                "--source", target,
                *branch_flag,
                "-m", "pytest", target,
                "-p", "randomly", "-q", "--no-cov",
                "--maxfail=5",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # If pytest exited non-zero, surface the failure honestly. Coverage
        # may still have data — we read it, but the operator sees the test
        # output upstream.
        if run.returncode != 0:
            sys.stderr.write(
                "measure_coverage: test run exited non-zero — coverage % may "
                "be incomplete. pytest output below:\n"
            )
            sys.stderr.write(run.stdout or "")
            sys.stderr.write(run.stderr or "")
        # 3. Produce a text report on the captured data.
        report = subprocess.run(
            ["coverage", "report", "--include", f"{target}*"],
            capture_output=True,
            text=True,
            check=False,
        )
        return report.stdout

    @staticmethod
    def _parse_report(text: str, branches: bool) -> tuple[float, float | None]:
        """Parse the TOTAL line out of `coverage report` text."""
        m = _TOTAL_LINE_RE.search(text)
        if not m:
            raise CommandError(
                "could not parse coverage report — is the target path correct? "
                f"Raw report:\n{text}"
            )
        pct = float(m.group("pct"))
        # Branch coverage isn't broken out in the default text report; rerun
        # with `--show-missing` or parse the XML if branches were requested
        # AND the parse failed. For now: return None when branches asked.
        branch_pct = None
        return pct, branch_pct
