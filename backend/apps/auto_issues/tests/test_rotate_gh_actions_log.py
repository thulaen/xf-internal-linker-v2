"""Tests for explicit GitHub Actions history rotation."""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase


class RotateGhActionsLogTests(SimpleTestCase):
    def test_rotation_moves_entries_before_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(
                root,
                [
                    _row("old", "2025-12-31T23:00:00+00:00"),
                    _row("new", "2026-01-02T00:00:00+00:00"),
                ],
            )
            output = StringIO()

            call_command("rotate_gh_actions_log", before="2026-01-01", repo_root=str(root), stdout=output)

            active = (root / "audit" / "github_actions_failures.jsonl").read_text(encoding="utf-8")
            archive = (root / "audit" / "github_actions_failures.archive.2025.jsonl").read_text(
                encoding="utf-8"
            )

        self.assertIn('"run_id": "new"', active)
        self.assertNotIn('"run_id": "old"', active)
        self.assertIn('"run_id": "old"', archive)
        self.assertIn("[GH ACTIONS LOG ROTATED: moved=1 kept=1]", output.getvalue())

    def test_rotation_preserves_autoissues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(root, [_row("old", "2025-12-31T23:00:00+00:00", autoissue_ids=[123])])

            call_command("rotate_gh_actions_log", before="2026-01-01", repo_root=str(root), stdout=StringIO())

            archive = (root / "audit" / "github_actions_failures.archive.2025.jsonl").read_text(
                encoding="utf-8"
            )

        self.assertIn('"autoissue_ids": [123]', archive)

    def test_rotation_is_opt_in_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(root, [_row("old", "2025-12-31T23:00:00+00:00")])

            self.assertFalse((root / "audit" / "github_actions_failures.archive.2025.jsonl").exists())
            self.assertIn("old", (root / "audit" / "github_actions_failures.jsonl").read_text())


def _write_history(root: Path, rows: list[dict]) -> None:
    audit = root / "audit"
    audit.mkdir(parents=True)
    (audit / "github_actions_failures.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _row(run_id: str, failed_at: str, *, autoissue_ids: list[int] | None = None) -> dict:
    return {
        "run_id": run_id,
        "workflow": "CI",
        "failed_at": failed_at,
        "failing_jobs": [{"name": "backend", "step": "pytest", "error_excerpt": "failed"}],
        "autoissue_ids": autoissue_ids or [1],
        "status": "open",
    }
