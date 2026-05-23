"""Regression tests for ``manage.py verify_rewrite_exemption`` (Phase K.2).

Covers the four exemption conditions named in
``docs/specs/fr-rewrite-quota-and-exemption.md`` so the command refuses
every shape of misrepresented evidence:

1. Structural shape — the evidence file is a JSON object with the
   required top-level + baseline + projection + citations keys.
2. Python remains — the touched area has zero legacy Python lines, or
   the lines remaining are declared as part of an ML/AI Python island.
3. Arithmetic match — the supplied ``projected_gain_pct`` matches the
   value the command recomputes from baseline and projected values
   within ``_GAIN_TOLERANCE_PCT`` (0.01).
4. Below threshold — the recomputed gain is strictly below
   ``projection.threshold_pct``; equal-to or above means a rewrite is
   justified and the exemption is refused.

Each test writes a small JSON evidence file to a tmpdir and invokes the
command via ``call_command`` so the round-trip mirrors the path the
``check-rewrite-quota`` pre-commit hook takes.
"""
from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


def _valid_evidence(**overrides) -> dict:
    """Return a baseline-passing evidence dict for use with ``write_json``."""
    payload = {
        "session_id": "test-session",
        "touched_paths": ["backend/apps/example/views.py"],
        "python_lines_remaining": 0,
        "python_island_declared_in_sticky": False,
        "baseline": {
            "metric": "p95_latency_ms",
            "value": 100.0,
            "source": "pyroscope",
            "function": "render",
            "workload": "render-1000-rows",
            "captured_at": "2026-05-23T00:00:00Z",
        },
        "projection": {
            "method": "extrapolation",
            "projected_value": 80.0,
            "projected_gain_pct": 20.0,
            "threshold_pct": 30.0,
            "verdict": "tiny_gain_or_no_python_remains",
        },
        "citations": ["doi:10.1145/361598.361623"],
    }
    payload.update(overrides)
    return payload


def _write_evidence(tmpdir: Path, payload: dict, name: str = "evidence.json") -> Path:
    path = tmpdir / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class HappyPathTests(SimpleTestCase):
    def test_valid_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = _write_evidence(Path(tmpdir), _valid_evidence())
            out = StringIO()
            call_command(
                "verify_rewrite_exemption",
                area=["backend/apps/example"],
                evidence_file=str(evidence),
                stdout=out,
            )
            self.assertIn("REWRITE QUOTA EXEMPTION VERIFIED", out.getvalue())


class StructuralFailureTests(SimpleTestCase):
    def test_missing_evidence_file_blocks(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "verify_rewrite_exemption",
                area=["backend/apps/example"],
                evidence_file="/nonexistent/evidence.json",
            )
        self.assertIn("does not exist", str(ctx.exception))

    def test_invalid_json_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "verify_rewrite_exemption",
                    area=["backend/apps/example"],
                    evidence_file=str(path),
                )
            self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_top_level_fields_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = _write_evidence(Path(tmpdir), {"session_id": "x"})
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "verify_rewrite_exemption",
                    area=["backend/apps/example"],
                    evidence_file=str(evidence),
                )
            self.assertIn("missing top-level fields", str(ctx.exception))

    def test_baseline_source_outside_allowlist_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _valid_evidence()
            payload["baseline"]["source"] = "guess"
            evidence = _write_evidence(Path(tmpdir), payload)
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "verify_rewrite_exemption",
                    area=["backend/apps/example"],
                    evidence_file=str(evidence),
                )
            self.assertIn("baseline.source must be one of", str(ctx.exception))

    def test_empty_citations_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _valid_evidence(citations=[])
            evidence = _write_evidence(Path(tmpdir), payload)
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "verify_rewrite_exemption",
                    area=["backend/apps/example"],
                    evidence_file=str(evidence),
                )
            self.assertIn("citations must be a non-empty list", str(ctx.exception))


class ArithmeticAndThresholdTests(SimpleTestCase):
    def test_recomputed_gain_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _valid_evidence()
            payload["projection"]["projected_gain_pct"] = 99.0
            evidence = _write_evidence(Path(tmpdir), payload)
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "verify_rewrite_exemption",
                    area=["backend/apps/example"],
                    evidence_file=str(evidence),
                )
            self.assertIn("does not match the recomputed value", str(ctx.exception))

    def test_gain_at_threshold_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _valid_evidence()
            payload["projection"]["projected_value"] = 70.0
            payload["projection"]["projected_gain_pct"] = 30.0
            evidence = _write_evidence(Path(tmpdir), payload)
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "verify_rewrite_exemption",
                    area=["backend/apps/example"],
                    evidence_file=str(evidence),
                )
            self.assertIn("at or above the threshold", str(ctx.exception))


class PythonRemainsTests(SimpleTestCase):
    def test_remaining_python_outside_island_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _valid_evidence()
            payload["python_lines_remaining"] = 42
            payload["python_island_declared_in_sticky"] = False
            evidence = _write_evidence(Path(tmpdir), payload)
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "verify_rewrite_exemption",
                    area=["backend/apps/example"],
                    evidence_file=str(evidence),
                )
            self.assertIn("legacy Python lines remain", str(ctx.exception))

    def test_remaining_python_inside_declared_island_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _valid_evidence()
            payload["python_lines_remaining"] = 42
            payload["python_island_declared_in_sticky"] = True
            evidence = _write_evidence(Path(tmpdir), payload)
            out = StringIO()
            call_command(
                "verify_rewrite_exemption",
                area=["backend/apps/pipeline/ml/model.py"],
                evidence_file=str(evidence),
                stdout=out,
            )
            self.assertIn("REWRITE QUOTA EXEMPTION VERIFIED", out.getvalue())

    def test_remaining_python_in_known_island_path_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _valid_evidence()
            payload["python_lines_remaining"] = 42
            payload["python_island_declared_in_sticky"] = False
            evidence = _write_evidence(Path(tmpdir), payload)
            out = StringIO()
            call_command(
                "verify_rewrite_exemption",
                area=["backend/apps/pipeline/ml/model.py"],
                evidence_file=str(evidence),
                stdout=out,
            )
            self.assertIn("REWRITE QUOTA EXEMPTION VERIFIED", out.getvalue())
