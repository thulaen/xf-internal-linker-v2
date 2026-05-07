"""Focused coverage for apps.audit.integrity helper functions."""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from apps.audit.integrity import (
    ARTEFACT_TABLE_SPECS,
    ArtefactTableSpec,
    _duplicate_groups_for_spec,
    verify_artefact_integrity,
)
from apps.audit.models import ErrorLog
from apps.content.models import ContentItem
from apps.crawler.models import CrawledPageMeta, CrawlSession


class ArtefactTableSpecTests(SimpleTestCase):
    def test_specs_keep_no_duplicates_identity_fields_visible(self) -> None:
        specs_by_name = {spec.name: spec for spec in ARTEFACT_TABLE_SPECS}

        self.assertEqual(
            specs_by_name["CrawledPageMeta"].duplicate_identity_fields,
            ("normalized_url", "content_hash"),
        )
        self.assertEqual(
            specs_by_name["SupersededEmbedding"].duplicate_identity_fields,
            (
                "content_item",
                "embedding_model_version",
                "content_hash",
                "content_version",
            ),
        )

    def test_verify_artefact_integrity_runs_registered_verifiers(self) -> None:
        first = Mock()
        second = Mock()
        specs = (
            ArtefactTableSpec("First", ContentItem, ("content_hash",), first),
            ArtefactTableSpec("Second", ContentItem, ("content_hash",), second),
        )

        with patch("apps.audit.integrity.ARTEFACT_TABLE_SPECS", specs):
            verify_artefact_integrity()

        first.assert_called_once_with()
        second.assert_called_once_with()


class CrawledPageMetaIntegrityTests(TestCase):
    def test_duplicate_groups_use_url_and_content_hash_together(self) -> None:
        self._make_meta("https://example.com/page", "hash-1")
        self._make_meta("https://example.com/page", "hash-2")

        groups = list(_duplicate_groups_for_spec(ARTEFACT_TABLE_SPECS[0]))

        self.assertEqual(groups, [])

    def test_verify_reports_duplicate_same_url_and_hash(self) -> None:
        self._make_meta("https://example.com/page", "hash-1")
        self._make_meta("https://example.com/page", "hash-1")

        verify_artefact_integrity()

        self.assertTrue(
            ErrorLog.objects.filter(
                job_type="integrity_check",
                step="CrawledPageMeta",
                error_message__contains="content_hash='hash-1'",
            ).exists()
        )

    def _make_meta(self, normalized_url: str, content_hash: str) -> CrawledPageMeta:
        session = CrawlSession.objects.create(site_domain="example.com")
        return CrawledPageMeta.objects.create(
            url=normalized_url,
            normalized_url=normalized_url,
            content_hash=content_hash,
            session=session,
        )
