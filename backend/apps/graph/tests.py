from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.graph.services import http_worker_client


class HttpWorkerClientTests(SimpleTestCase):
    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080/api/v1/status",
    )
    @patch("apps.graph.services.http_worker_client.request.urlopen")
    def test_client_strips_status_suffix_from_base_url(self, mock_urlopen):
        response = MagicMock()
        response.getcode.return_value = 200
        response.read.return_value = b'{"checked": []}'
        mock_urlopen.return_value.__enter__.return_value = response

        http_worker_client.check_health(["https://example.com/health"])

        outgoing_request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            outgoing_request.full_url,
            "http://http-worker-api:8080/api/v1/health/check",
        )
