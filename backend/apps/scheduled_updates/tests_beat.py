"""Beat-schedule sanity checks (PR-B.6).

Guards the three Scheduled Updates beat entries against regressions:

- they exist in CELERY_BEAT_SCHEDULE
- they point at the right dotted-path task names
- the runner tick fires only inside the 13:00-22:59 window (no 23:00+
  ticks that would be refused anyway)
- the prune task is scheduled late in the window (22:45) so nothing
  runs past it
"""

from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase


class BeatScheduleTests(SimpleTestCase):
    def setUp(self) -> None:
        self.schedule = settings.CELERY_BEAT_SCHEDULE

    def test_runner_tick_entry_exists(self) -> None:
        assert "scheduled-updates-runner-tick" in self.schedule
        entry = self.schedule["scheduled-updates-runner-tick"]
        assert entry["task"] == "scheduled_updates.run_next_scheduled_job"

    def test_runner_tick_inside_window_only(self) -> None:
        entry = self.schedule["scheduled-updates-runner-tick"]
        cron = entry["schedule"]
        # crontab.hour is a set of hour-ints after parsing "13-22".
        assert set(cron.hour) == set(range(13, 23))
        # Every 5 minutes → 12 ticks per hour.
        assert len(cron.minute) == 12

    def test_detect_stalled_entry(self) -> None:
        assert "scheduled-updates-detect-stalled" in self.schedule
        entry = self.schedule["scheduled-updates-detect-stalled"]
        assert entry["task"] == "scheduled_updates.detect_stalled_jobs"
        cron = entry["schedule"]
        assert set(cron.hour) == set(range(13, 23))
        # At :30 past the hour.
        assert set(cron.minute) == {30}

    def test_prune_alerts_entry_is_late_in_window(self) -> None:
        assert "scheduled-updates-prune-resolved-alerts" in self.schedule
        entry = self.schedule["scheduled-updates-prune-resolved-alerts"]
        assert entry["task"] == "scheduled_updates.prune_resolved_alerts"
        cron = entry["schedule"]
        assert set(cron.hour) == {22}
        assert set(cron.minute) == {45}

    def test_no_scheduled_updates_entry_fires_after_23(self) -> None:
        """Paranoid guard: none of our entries target hour >= 23."""
        for name, entry in self.schedule.items():
            if not name.startswith("scheduled-updates-"):
                continue
            cron = entry["schedule"]
            if not hasattr(cron, "hour"):
                continue
            assert max(cron.hour) < 23, (
                f"beat entry {name!r} targets hour {max(cron.hour)} "
                f"— outside the 13:00-23:00 window"
            )
