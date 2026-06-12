from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.auto_issues.services.session_start_payload import PayloadError, StartupPayload


class SessionStartPayloadTestCase(SimpleTestCase):
    @patch("apps.auto_issues.management.commands.session_start_payload.read_helper_payload")
    def test_command_success(self, mock_read):
        payload = StartupPayload(
            version=1,
            generated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            markers=[],
            autoissues=[],
            body="payload_body_content",
        )
        mock_read.return_value = payload
        
        out = StringIO()
        call_command("session_start_payload", url="http://dummy", stdout=out)
        self.assertIn("payload_body_content", out.getvalue())
        mock_read.assert_called_once_with("http://dummy", timeout_seconds=5.0)

    @patch("apps.auto_issues.management.commands.session_start_payload.read_helper_payload")
    def test_command_error(self, mock_read):
        mock_read.side_effect = PayloadError("test payload error")
        with self.assertRaises(CommandError) as ctx:
            call_command("session_start_payload", url="http://dummy")
        self.assertIn("test payload error", str(ctx.exception))
