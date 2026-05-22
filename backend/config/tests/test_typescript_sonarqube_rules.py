"""Regression tests that pin SonarSource TypeScript rule compliance.

This file does NOT execute TypeScript or karma.  Instead it parses the
frontend source files as plain text and asserts the specific
rule-violating patterns are absent.  The patterns themselves were
documented in `AutoIssue` rows #947 (S2871), #1004 + #1102 (S3776),
#1008 + #1009 + #1081 + #1082 (S3735) — see
`config/tests/test_settings_no_wildcard.py` for the parallel Python
pattern.

Running the SonarSource scanner against the live SonarQube server is the
authoritative check.  These tests catch regressions BEFORE the scanner
re-imports an open AutoIssue for the same line.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase


def _frontend_root() -> Path:
    """Locate ``frontend/src/app/`` regardless of where the test runs.

    Inside the backend container ``/repo`` mounts the full repo (see
    ``docker-compose.yml`` — backend mounts ``..:/repo``).  On a host
    workstation the tests live under ``backend/`` so walking up three
    parents lands on the repo root.  Try both.
    """
    candidates = (
        Path("/repo/frontend/src/app"),
        Path(__file__).resolve().parents[3] / "frontend" / "src" / "app",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    msg = (
        "Cannot locate frontend/src/app — neither /repo nor walking up "
        "from this test file resolved.  Tried: "
        + ", ".join(str(c) for c in candidates)
    )
    raise FileNotFoundError(msg)


_FRONTEND_DIR = _frontend_root()


def _read(rel: str) -> str:
    return (_FRONTEND_DIR / rel).read_text(encoding="utf-8")


class S3735_NoBareVoidStatement(SimpleTestCase):
    """`typescript:S3735` — `void <expr>;` as a statement is forbidden.

    The acceptable alternatives are documented in the rule:
      - `await <expr>` for async work
      - `<expr>.catch(...)` for Promise side effects
      - `const _x = <expr>;` for value-bearing expressions whose result
        is intentionally unused
    """

    _VOID_STATEMENT = re.compile(r"(^|;|\{)\s*void\s+[^;]+;", re.MULTILINE)

    def test_otel_bootstrap_has_no_void_statement(self) -> None:
        source = _read("core/observability/otel-bootstrap.ts")
        violation = self._VOID_STATEMENT.search(source)
        self.assertIsNone(
            violation,
            msg=(
                "core/observability/otel-bootstrap.ts still contains a "
                f"`void <expr>;` statement at position {violation.start() if violation else 'N/A'}. "
                "Remove dead void-expression statements or use "
                "`await ...` / `.catch(...)` / `const _x = ...`."
            ),
        )

    def test_global_link_interceptor_has_no_void_statement(self) -> None:
        source = _read("core/services/global-link-interceptor.service.ts")
        violation = self._VOID_STATEMENT.search(source)
        self.assertIsNone(
            violation,
            msg=(
                "core/services/global-link-interceptor.service.ts still "
                f"contains a `void <expr>;` statement at position "
                f"{violation.start() if violation else 'N/A'}. "
                "Use `<expr>.catch(...)` to handle the rejected Promise "
                "branch."
            ),
        )


class S2871_SortHasExplicitCompareFunction(SimpleTestCase):
    """`typescript:S2871` — `.sort()` without a compareFunction is forbidden."""

    _BARE_SORT = re.compile(r"\.sort\(\s*\)")

    def test_undo_timeline_sort_has_compare_function(self) -> None:
        source = _read("audit/undo-timeline/undo-timeline.component.ts")
        violation = self._BARE_SORT.search(source)
        self.assertIsNone(
            violation,
            msg=(
                "audit/undo-timeline/undo-timeline.component.ts still "
                "calls `.sort()` without a compare function "
                f"(position {violation.start() if violation else 'N/A'}). "
                "Even for string arrays the explicit form "
                "`(a, b) => a.localeCompare(b)` is the SonarSource "
                "recommendation."
            ),
        )


class S3776_HelperExtractionApplied(SimpleTestCase):
    """`typescript:S3776` — cognitive complexity must stay below 15.

    A faithful cognitive-complexity calculation requires the SonarSource
    engine.  As a regression proxy, this test asserts that the
    helper-extraction refactor was applied — each flagged source file
    must define specific helpers that split the high-complexity branch
    tree into pieces.  If a future change re-inlines a helper or
    introduces a new high-complexity block, this test fails before the
    next SonarQube scan re-opens the AutoIssue.
    """

    def test_error_interceptor_has_extracted_helpers(self) -> None:
        source = _read("core/interceptors/error.interceptor.ts")
        # First-round helpers (interceptor body)
        first_round = ("_retryDelayStrategy", "_showRateLimitSnackbar", "_messageForNetworkOrStatus")
        # Second-round helpers (extractServerErrorMessage body — SonarQube
        # still reported cognitive complexity 17 > 15 after the first round
        # so the function had to be split further)
        second_round = ("_extractDetailString", "_extractMessageString", "_findFirstStringInBody")
        for helper in first_round + second_round:
            self.assertIn(
                f"function {helper}",
                source,
                msg=(
                    f"core/interceptors/error.interceptor.ts is missing "
                    f"helper `{helper}` — the S3776 refactor extracts "
                    "the retry-delay, rate-limit, status-mapping, AND "
                    "server-message body-parsing logic into named "
                    "helpers so every function stays under the cognitive-"
                    "complexity ceiling (15)."
                ),
            )

    def test_parse_worker_has_extracted_helpers(self) -> None:
        source = _read("core/services/parse-worker.service.ts")
        for helper in ("_tokeniseCsv", "_consumeQuotedChar", "_shapeCsvRows"):
            self.assertIn(
                f"function {helper}",
                source,
                msg=(
                    f"core/services/parse-worker.service.ts is missing "
                    f"helper `{helper}` — the S3776 refactor splits the "
                    "CSV state machine, the quoted-char rule, and the "
                    "header-shaping into three named helpers."
                ),
            )
