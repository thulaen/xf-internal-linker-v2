"""Tests for suggestion serializer API schema annotations."""

from __future__ import annotations

from django.test import SimpleTestCase
from drf_spectacular.drainage import get_override
from drf_spectacular.types import OpenApiTypes

from apps.suggestions.serializers import SuggestionDetailSerializer


class SuggestionDetailSerializerSchemaTests(SimpleTestCase):
    def test_link_freshness_diagnostics_declares_object_schema(self) -> None:
        field_schema = get_override(
            SuggestionDetailSerializer.get_link_freshness_diagnostics,
            "field",
        )

        self.assertEqual(field_schema, OpenApiTypes.OBJECT)

    def test_telemetry_instrumentation_declares_object_schema(self) -> None:
        field_schema = get_override(
            SuggestionDetailSerializer.get_telemetry_instrumentation,
            "field",
        )

        self.assertEqual(field_schema, OpenApiTypes.OBJECT)
