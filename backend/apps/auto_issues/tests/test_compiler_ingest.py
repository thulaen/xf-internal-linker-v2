"""Fast tests for compiler_ingest.py (warning text -> deduped SOURCE_COMPILER AutoIssues).

SimpleTestCase with the DB seam mocked (upsert_dedup + AutoIssue.objects), so the
whole suite runs in milliseconds and the scoped-mutation gate can re-run it per
mutant (the slow Django-TestCase version blew past the 30-minute mutation budget,
the same trap fixed for the pgexporter picker). Covers every line of
compiler_ingest.py: the dry-run vs filing branches, the dedup-key / short-hash /
external-id helpers (including the long-path truncation path), the error-vs-warning
severity mapping, the col-present / col-absent location formatting, the detail
fallback, and the occurrence-count helper. Per-language PARSING is covered by
test_compiler_warnings.py (the pure parser at 100%).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import compiler_ingest
from apps.auto_issues.services.compiler_warnings import CompilerWarning


def _warn(**kw):
    base = dict(language="cpp", file="src/a.cpp", line=10, col=4,
                code="-Wunused", message="unused variable 'x'", severity="warning")
    base.update(kw)
    return CompilerWarning(**base)


def _objects(first=None):
    mgr = MagicMock(name="AutoIssue.objects")
    chain = MagicMock(name="qs")
    mgr.filter.return_value = chain
    chain.exclude.return_value = chain
    chain.first.return_value = first
    return mgr


class IngestTests(SimpleTestCase):
    def test_dry_run_parses_but_files_nothing(self):
        with patch.object(compiler_ingest, "parse_warnings",
                          return_value=[_warn(), _warn(line=20)]), \
             patch.object(compiler_ingest, "upsert_dedup") as upsert:
            result = compiler_ingest.ingest_compiler_warnings("x", "cpp", dry_run=True)
        self.assertEqual(result, {"parsed": 2, "filed": 0})
        upsert.assert_not_called()

    def test_files_one_autoissue_per_warning(self):
        with patch.object(compiler_ingest, "parse_warnings",
                          return_value=[_warn(), _warn(line=20)]), \
             patch.object(compiler_ingest, "upsert_dedup") as upsert, \
             patch.object(compiler_ingest.AutoIssue, "objects", _objects(first=None)):
            result = compiler_ingest.ingest_compiler_warnings("x", "cpp")
        self.assertEqual(result, {"parsed": 2, "filed": 2})
        self.assertEqual(upsert.call_count, 2)

    def test_warning_maps_to_low_severity_and_compiler_source(self):
        with patch.object(compiler_ingest, "upsert_dedup") as upsert, \
             patch.object(compiler_ingest.AutoIssue, "objects", _objects(first=None)):
            compiler_ingest._file_warning(_warn(severity="warning"))
        kwargs = upsert.call_args.kwargs
        self.assertEqual(kwargs["source"], AutoIssue.SOURCE_COMPILER)
        self.assertEqual(kwargs["severity"], AutoIssue.SEVERITY_LOW)
        self.assertAlmostEqual(kwargs["priority_score"], 0.35)
        self.assertEqual(kwargs["affected_files"], ["src/a.cpp"])
        self.assertIn("10:4", kwargs["description"])  # col present in location

    def test_error_maps_to_high_severity(self):
        with patch.object(compiler_ingest, "upsert_dedup") as upsert, \
             patch.object(compiler_ingest.AutoIssue, "objects", _objects(first=None)):
            compiler_ingest._file_warning(_warn(severity="error"))
        kwargs = upsert.call_args.kwargs
        self.assertEqual(kwargs["severity"], AutoIssue.SEVERITY_HIGH)
        self.assertAlmostEqual(kwargs["priority_score"], 0.7)

    def test_location_without_col(self):
        with patch.object(compiler_ingest, "upsert_dedup") as upsert, \
             patch.object(compiler_ingest.AutoIssue, "objects", _objects(first=None)):
            compiler_ingest._file_warning(_warn(col=None))
        self.assertIn("src/a.cpp:10 ", upsert.call_args.kwargs["description"])

    def test_detail_falls_back_to_code_when_message_empty(self):
        with patch.object(compiler_ingest, "upsert_dedup") as upsert, \
             patch.object(compiler_ingest.AutoIssue, "objects", _objects(first=None)):
            compiler_ingest._file_warning(_warn(message="", code="-Wx"))
        self.assertIn("-Wx", upsert.call_args.kwargs["title"])

    def test_dedup_key_uses_message_when_no_code(self):
        key = compiler_ingest._dedup_key(_warn(code="", message="m" * 80))
        self.assertTrue(key.startswith("compiler:cpp:src/a.cpp:10:"))
        self.assertIn("m" * 48, key)
        self.assertNotIn("m" * 49, key)

    def test_short_hash_is_16_hex_chars(self):
        h = compiler_ingest._short_hash("compiler:cpp:x:1:y")
        self.assertEqual(len(h), 16)
        int(h, 16)  # raises if not hex

    def test_external_id_passes_short_keys_through(self):
        self.assertEqual(compiler_ingest._external_id("short:key", "abcd"), "short:key")

    def test_external_id_truncates_long_keys_and_appends_hash(self):
        long_key = "compiler:cpp:" + "d/" * 200 + "file.cpp:1:code"
        fp = "0123456789abcdef"
        out = compiler_ingest._external_id(long_key, fp)
        self.assertLessEqual(len(out), compiler_ingest._EXTERNAL_ID_MAX)
        self.assertTrue(out.endswith(fp))

    def test_next_occurrence_count_increments_existing(self):
        with patch.object(compiler_ingest.AutoIssue, "objects",
                          _objects(first=MagicMock(occurrence_count=3))):
            self.assertEqual(compiler_ingest._next_occurrence_count("eid"), 4)

    def test_next_occurrence_count_one_when_missing(self):
        with patch.object(compiler_ingest.AutoIssue, "objects", _objects(first=None)):
            self.assertEqual(compiler_ingest._next_occurrence_count("eid"), 1)

    def test_next_occurrence_count_treats_null_as_zero(self):
        with patch.object(compiler_ingest.AutoIssue, "objects",
                          _objects(first=MagicMock(occurrence_count=None))):
            self.assertEqual(compiler_ingest._next_occurrence_count("eid"), 1)
