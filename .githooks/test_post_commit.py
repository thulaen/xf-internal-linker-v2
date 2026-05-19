"""Unit tests for the .githooks/post-commit decision-point shim."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

import _hook_helpers  # noqa: E402


SCRIPT_PATH = HOOK_DIR / "post-commit"


class PostCommitHookTests(unittest.TestCase):
    """Verify the public contract exposed by the shell hook."""

    def _script(self) -> str:
        return SCRIPT_PATH.read_text(encoding="utf-8")

    def test_hook_is_classified_as_production_source(self) -> None:
        self.assertTrue(_hook_helpers.is_production_source(".githooks/post-commit"))

    def test_hook_calls_decision_point_for_head_commit(self) -> None:
        script = self._script()
        self.assertIn("head_hash=\"$(git rev-parse HEAD", script)
        self.assertIn("python manage.py decision_point --commit \"$head_hash\"", script)
        self.assertIn("docker compose exec -T backend", script)

    def test_missing_head_exits_zero_with_warning(self) -> None:
        script = self._script()
        self.assertIn("[decision-point] (no HEAD commit", script)
        self.assertIn("exit 0", script)

    def test_missing_backend_tells_operator_how_to_backfill(self) -> None:
        script = self._script()
        self.assertIn("backend container not running; skipping", script)
        self.assertIn("decision_point --commit ${head_hash:0:7}", script)
        self.assertIn("exit 0", script)

    def test_decision_point_failure_is_non_blocking(self) -> None:
        script = self._script()
        self.assertIn("command exited non-zero; rerun manually after fixing", script)
        self.assertTrue(script.rstrip().endswith("exit 0"))


if __name__ == "__main__":
    unittest.main()
