from unittest.mock import Mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from requests.auth import HTTPBasicAuth

from apps.sync.models import SyncJob
from apps.sync.serializers import SyncJobSerializer
from apps.sync.services.wordpress_api import WordPressAPIClient


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
