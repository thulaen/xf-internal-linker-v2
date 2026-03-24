from unittest.mock import Mock

from django.test import SimpleTestCase
from requests.auth import HTTPBasicAuth

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
