import json
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase
from apps.core.services.linear_api import LinearClient
from django.conf import settings

class AutoIssueMock:
    def __init__(self, title, description, status, external_id):
        self.title = title
        self.description = description
        self.status = status
        self.external_id = external_id

class PaperTrailEntryMock:
    def __init__(self, title, abstract, status, fingerprint):
        self.title = title
        self.abstract = abstract
        self.status = status
        self.fingerprint = fingerprint

class TestLinearAPI(SimpleTestCase):
    def setUp(self):
        self.client = LinearClient()

    @patch('apps.core.services.linear_api.requests.post')
    def test_sync_autoissue_to_linear(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        issue = AutoIssueMock(title="Test Issue", description="Test Desc", status="open", external_id="ext-123")
        self.client.sync_autoissue_to_linear(issue)

        self.assertTrue(mock_post.called)
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.graphql.linear.app/")
        payload = kwargs.get('json', {})
        self.assertIn("mutation", payload.get('query', ''))
        self.assertIn("Test Issue", payload.get('query', ''))
        self.assertIn("Test Desc", payload.get('query', ''))

    @patch('apps.core.services.linear_api.requests.post')
    def test_sync_papertrail_to_linear(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        entry = PaperTrailEntryMock(title="Test Trail", abstract="Abstract", status="closed", fingerprint="fp-456")
        self.client.sync_papertrail_to_linear(entry)

        self.assertTrue(mock_post.called)
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.graphql.linear.app/")
        payload = kwargs.get('json', {})
        self.assertIn("mutation", payload.get('query', ''))
        self.assertIn("Test Trail", payload.get('query', ''))
        self.assertIn("Abstract", payload.get('query', ''))

    @patch('apps.core.services.linear_api.requests.post')
    def test_fetch_open_linear_issues(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": {
                "issues": {
                    "nodes": [
                        {"id": "iss-1", "title": "Issue 1", "url": "http://linear/iss-1"},
                        {"id": "iss-2", "title": "Issue 2", "url": "http://linear/iss-2"}
                    ]
                }
            }
        }
        mock_post.return_value = mock_response

        issues = self.client.fetch_open_linear_issues(limit=2)
        
        self.assertTrue(mock_post.called)
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]['id'], "iss-1")
