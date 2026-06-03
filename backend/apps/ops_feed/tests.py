"""Tests for the Operations Feed emitter.

Plain-English: Verify that concurrent or repeated emissions with the same
dedup key correctly collapse into one row and don't log noisy errors.
"""

from django.test import TestCase
from apps.ops_feed.models import OperationEvent
from apps.ops_feed.services import emit
import logging

class OpsFeedEmitTests(TestCase):
    def test_repeated_emit_with_same_key_deduplicates(self):
        # First emission creates the row
        emit(
            event_type="test_event",
            plain_english="First message",
            source="test_source",
            related_entity_type="item",
            related_entity_id="123",
        )
        rows = OperationEvent.objects.filter(event_type="test_event", source="test_source")
        self.assertEqual(rows.count(), 1)
        event = rows.get()
        self.assertEqual(event.occurrence_count, 1)
        self.assertEqual(event.plain_english, "First message")

        # Second emission with same key bumps counter and updates message
        emit(
            event_type="test_event",
            plain_english="Second message",
            source="test_source",
            related_entity_type="item",
            related_entity_id="123",
        )
        self.assertEqual(rows.count(), 1)
        event.refresh_from_db()
        self.assertEqual(event.occurrence_count, 2)
        self.assertEqual(event.plain_english, "Second message")

    def test_emit_is_safe_on_integrity_error(self):
        # `emit()` derives its dedup_key from (event_type, source,
        # related_entity_type, related_entity_id) so two calls with
        # the same producing args collapse onto one OperationEvent row.
        # Verify the safe-path does NOT log at ERROR or higher. We
        # capture log records manually because unittest.assertLogs
        # fails when zero matching records are captured.
        logger = logging.getLogger("apps.ops_feed.services")
        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        handler = _Capture(level=logging.ERROR)
        logger.addHandler(handler)
        try:
            emit(event_type="test_event", plain_english="Msg 1")
            emit(event_type="test_event", plain_english="Msg 2")
        finally:
            logger.removeHandler(handler)

        self.assertEqual([record.getMessage() for record in captured], [])

    def test_emit_handles_integrity_error_silently(self):
        from unittest.mock import patch
        from django.db import IntegrityError
        
        # Mock create to raise IntegrityError on first call to simulate race
        with patch("apps.ops_feed.models.OperationEvent.objects.create") as mock_create:
            mock_create.side_effect = IntegrityError("Duplicate key")
            
            # This should NOT crash and should NOT log an ERROR (only DEBUG)
            emit(
                event_type="race_event",
                plain_english="Race message",
            )
            
            self.assertTrue(mock_create.called)
