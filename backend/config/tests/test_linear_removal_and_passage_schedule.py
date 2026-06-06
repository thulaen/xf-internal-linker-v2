"""Settings regressions for two changes in this slice.

1. ``config/settings/celery_schedules.py`` moved the
   ``refresh-passage-embeddings`` beat entry off a sliding ``minute="*/30"``
   (every 30 minutes, phase-drifting) onto two fixed wall-clock minutes
   ``minute="12,42"`` so the embedding refresh fires at predictable :12 and
   :42 past every hour. This test reads the live ``CELERY_BEAT_SCHEDULE`` and
   pins the parsed crontab minute set so a future edit that re-introduces a
   sliding interval (or drops one of the two minutes) fails here.

2. ``config/settings/base.py`` deleted the ``LINEAR_API_KEY`` setting when the
   Linear sync was decoupled from the paper-trail save path. This test proves
   the Django settings object no longer carries that attribute, so a stray
   re-import of the removed key cannot silently resurrect a dead integration.
"""

from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase


class RefreshPassageEmbeddingsScheduleTests(SimpleTestCase):
    def test_entry_exists_and_targets_pipeline_task(self) -> None:
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn("refresh-passage-embeddings", schedule)
        entry = schedule["refresh-passage-embeddings"]
        self.assertEqual(entry["task"], "pipeline.refresh_passage_embeddings")
        self.assertEqual(entry["options"]["queue"], "pipeline")

    def test_runs_only_at_minute_12_and_42(self) -> None:
        entry = settings.CELERY_BEAT_SCHEDULE["refresh-passage-embeddings"]
        cron = entry["schedule"]
        # crontab parses "12,42" into the minute set {12, 42}. The old
        # "*/30" produced {0, 30}; asserting the exact set kills both a
        # revert to */30 and an off-by-one minute edit.
        self.assertEqual(set(cron.minute), {12, 42})
        self.assertNotIn(0, set(cron.minute))
        self.assertNotIn(30, set(cron.minute))


class LinearApiKeyRemovedTests(SimpleTestCase):
    def test_settings_no_longer_exposes_linear_api_key(self) -> None:
        # The attribute was deleted from base.py; Django's lazy settings must
        # not surface it. ``hasattr`` returns False for a removed setting.
        self.assertFalse(
            hasattr(settings, "LINEAR_API_KEY"),
            msg="LINEAR_API_KEY was removed from base.py when the Linear sync "
            "was decoupled; it must not reappear on the settings object.",
        )
