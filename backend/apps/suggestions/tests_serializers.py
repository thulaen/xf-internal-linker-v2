"""Convention-named discovery shim for apps/suggestions/serializers.py.

The mutation gate discovers ``tests_<stem>.py`` next to ``<stem>.py``. The proven
coverage for the ``serializers.py`` change — the ``@extend_schema_field`` schema
annotations on ``SuggestionDetailSerializer`` — lives in the differently-suffixed
``tests_serializers_schema.py`` next to this file. To avoid duplicating those
asserted overrides (which would drift), this shim re-exports that test class under
the discoverable name so the same assertions run when the gate collects
``tests_serializers.py``.

The re-exported class is a ``SimpleTestCase`` that reads the ``drf_spectacular``
field override off the serializer methods — no database, no network — so this is
hang-safe for the mutation gate.
"""

from __future__ import annotations

from apps.suggestions.tests_serializers_schema import (  # noqa: F401
    SuggestionDetailSerializerSchemaTests,
)

__all__ = ["SuggestionDetailSerializerSchemaTests"]
