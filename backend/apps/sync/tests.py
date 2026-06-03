"""Test suite for the sync app."""

from unittest.mock import Mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from requests.auth import HTTPBasicAuth

from apps.sync.models import SyncJob
from apps.sync.serializers import SyncJobSerializer
from apps.sync.services.wordpress_api import WordPressAPIClient
from apps.sync.services.xenforo_api import XenForoAPIClient
import requests

class XenForoApiClientTests(SimpleTestCase):
    @patch('apps.sync.services.xenforo_api.requests.get')
    @patch('apps.sync.services.xenforo_api.logger.warning')
    def test_api_client_retries_and_raises(self, mock_warning, mock_get):
        client = XenForoAPIClient(base_url="https://example.com", api_key="test-key")
        mock_get.side_effect = requests.exceptions.ConnectionError("Mocked failure")
        
        with self.assertRaises(requests.exceptions.ConnectionError):
            client._get("test/")
            
        # Should attempt 3 times (the initial plus 2 retries)
        self.assertEqual(mock_get.call_count, 3)
        # Should log a warning (not error) for the failures
        self.assertEqual(mock_warning.call_count, 3)


class WordPressApiClientTests(SimpleTestCase):
    def test_public_client_uses_no_basic_auth(self):
        client = WordPressAPIClient(base_url="https://blog.example.com")

        self.assertFalse(client.has_credentials)
        self.assertIsNone(client.session.auth)

    def test_authenticated_client_configures_basic_auth_and_pagination(self):
        client = WordPressAPIClient(
            base_url="https://blog.example.com",
            username="editor",
            app_password="app-pass",
        )
        response = Mock()
        response.headers = {"X-WP-TotalPages": "3"}
        response.json.return_value = [{"id": 1, "title": {"rendered": "Post"}}]
        response.raise_for_status.return_value = None
        client.session.get = Mock(return_value=response)

        records, total_pages = client.get_posts(page=2, status="private")

        self.assertTrue(client.has_credentials)
        self.assertIsInstance(client.session.auth, HTTPBasicAuth)
        self.assertEqual(total_pages, 3)
        self.assertEqual(records[0]["id"], 1)
        client.session.get.assert_called_once()


class WordPressVerifyCredentialsTests(SimpleTestCase):
    """Issue #2027: verify_credentials must not raise JSONDecodeError on empty body."""

    def _make_client(self):
        return WordPressAPIClient(
            base_url="https://blog.example.com",
            username="editor",
            app_password="app-pass",
        )

    def test_verify_credentials_returns_ok_false_on_empty_body(self):
        """Empty response body must not raise JSONDecodeError (issue #2027)."""
        client = self._make_client()
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.content = b""
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("No JSON")
        client.session.get = Mock(return_value=resp)
        with patch("apps.sources.api_rate_limiter.rate_limited"):
            result = client.verify_credentials()
        self.assertFalse(result["ok"])

    def test_verify_credentials_returns_ok_true_on_valid_json(self):
        """Normal 200 with valid JSON still works."""
        client = self._make_client()
        resp = Mock()
        resp.status_code = 200
        resp.text = '{"name": "Alice"}'
        resp.content = b'{"name": "Alice"}'
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"name": "Alice"}
        client.session.get = Mock(return_value=resp)
        with patch("apps.sources.api_rate_limiter.rate_limited"):
            result = client.verify_credentials()
        self.assertTrue(result["ok"])
        self.assertEqual(result["display_name"], "Alice")


class SyncJobResumeApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="sync-resume-user",
            password="pass",
        )
        self.client.force_authenticate(user=user)

    @patch("apps.pipeline.tasks.dispatch_import_content")
    def test_resume_dispatches_failed_resumable_job(self, dispatch_import_content):
        job = SyncJob.objects.create(
            source="api",
            mode="full",
            status="failed",
            checkpoint_stage="ingest",
            checkpoint_last_item_id=42,
            checkpoint_items_processed=11,
            is_resumable=True,
        )

        response = self.client.post(f"/api/sync-jobs/{job.job_id}/resume/", {})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
        dispatch_import_content.assert_called_once_with(
            mode="full",
            source="api",
            file_path=None,
            job_id=str(job.job_id),
        )

    @patch("apps.pipeline.tasks.dispatch_import_content")
    def test_resume_rejects_blank_checkpoint(self, dispatch_import_content):
        job = SyncJob.objects.create(
            source="api",
            mode="full",
            status="failed",
            checkpoint_stage="",
            is_resumable=True,
        )

        response = self.client.post(f"/api/sync-jobs/{job.job_id}/resume/", {})

        self.assertEqual(response.status_code, 400)
        dispatch_import_content.assert_not_called()

    def test_serializer_exposes_resume_checkpoint_fields(self):
        job = SyncJob.objects.create(
            source="wp",
            mode="titles",
            status="paused",
            checkpoint_stage="embed",
            checkpoint_last_item_id=7,
            checkpoint_items_processed=3,
            is_resumable=True,
        )

        data = SyncJobSerializer(job).data

        self.assertTrue(data["is_resumable"])
        self.assertEqual(data["checkpoint_stage"], "embed")
        self.assertEqual(data["checkpoint_last_item_id"], 7)
        self.assertEqual(data["checkpoint_items_processed"], 3)
