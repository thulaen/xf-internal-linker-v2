"""Regression: disk-pressure alerts must actually persist an OperatorAlert.

`_emit_alert` called `OperatorAlert.objects.create(..., body=msg)`, but the
model field is `message`, not `body`. The create() raised
`TypeError: OperatorAlert() got unexpected keyword arguments: 'body'`, which the
best-effort `except` swallowed — so NO alert row was ever created and the Celery
worker logged a warning on every disk-pressure event (a 1800+/hour error burst).
The model also requires a meaningful `event_type`.
"""

from django.test import TestCase

from apps.notifications.models import OperatorAlert
from apps.pipeline.services.disk_pressure import _emit_alert


class DiskPressureAlertTests(TestCase):
    def test_emit_alert_persists_operator_alert_with_message(self):
        _emit_alert("YELLOW", free_gb=1.5)
        alert = OperatorAlert.objects.filter(title="Disk pressure YELLOW").first()
        self.assertIsNotNone(alert, "disk-pressure alert was not persisted")
        self.assertIn("1.5 GB free", alert.message)
        self.assertEqual(alert.event_type, "disk.pressure")

    def test_emit_alert_maps_state_to_severity(self):
        _emit_alert("RED", free_gb=0.5)
        alert = OperatorAlert.objects.filter(title="Disk pressure RED").first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, OperatorAlert.SEVERITY_ERROR)
