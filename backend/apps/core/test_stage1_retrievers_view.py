"""Tests for the Stage-1 retriever settings endpoint (Group C wiring)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.views_stage1_retrievers import get_stage1_retriever_settings


class Stage1RetrieverSettingsViewTests(TestCase):
    URL = "/api/settings/stage1-retrievers/"

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="op", password="pw", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_returns_defaults_on_cold_start(self) -> None:
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["lexical_retriever_enabled"], False)
        self.assertEqual(body["query_expansion_retriever_enabled"], False)

    def test_put_persists_both_flags(self) -> None:
        resp = self.client.put(
            self.URL,
            data={
                "lexical_retriever_enabled": True,
                "query_expansion_retriever_enabled": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # Round-trip via the read helper.
        self.assertEqual(
            get_stage1_retriever_settings(),
            {
                "lexical_retriever_enabled": True,
                "query_expansion_retriever_enabled": True,
            },
        )

    def test_put_partial_keeps_other_flag(self) -> None:
        # Set both to True first.
        self.client.put(
            self.URL,
            data={
                "lexical_retriever_enabled": True,
                "query_expansion_retriever_enabled": True,
            },
            format="json",
        )
        # PUT only the lexical flag back to False.
        resp = self.client.put(
            self.URL,
            data={"lexical_retriever_enabled": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        snap = get_stage1_retriever_settings()
        self.assertFalse(snap["lexical_retriever_enabled"])
        # The other flag stays True (PUT keeps current values for
        # missing keys).
        self.assertTrue(snap["query_expansion_retriever_enabled"])

    def test_string_inputs_coerce_correctly(self) -> None:
        """API consumers may send strings for booleans (e.g. legacy clients)."""
        resp = self.client.put(
            self.URL,
            data={
                "lexical_retriever_enabled": "yes",
                "query_expansion_retriever_enabled": "off",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        snap = get_stage1_retriever_settings()
        self.assertTrue(snap["lexical_retriever_enabled"])
        self.assertFalse(snap["query_expansion_retriever_enabled"])

    def test_unauthenticated_request_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get(self.URL)
        self.assertIn(resp.status_code, (401, 403))

    def test_default_registry_picks_up_persisted_flags(self) -> None:
        """End-to-end: flipping the AppSetting flag on changes the
        retriever list returned by ``default_retrievers``."""
        from apps.pipeline.services.candidate_retrievers import (
            LexicalRetriever,
            QueryExpansionRetriever,
            SemanticRetriever,
            default_retrievers,
        )

        # Cold start.
        regs = default_retrievers()
        self.assertEqual(len(regs), 1)
        self.assertIsInstance(regs[0], SemanticRetriever)

        # Flip both flags via the API.
        self.client.put(
            self.URL,
            data={
                "lexical_retriever_enabled": True,
                "query_expansion_retriever_enabled": True,
            },
            format="json",
        )

        regs2 = default_retrievers()
        self.assertEqual(len(regs2), 3)
        names = [r.name for r in regs2]
        self.assertEqual(names, ["semantic", "lexical", "query_expansion"])
        self.assertIsInstance(regs2[1], LexicalRetriever)
        self.assertIsInstance(regs2[2], QueryExpansionRetriever)
