from django.test import SimpleTestCase
from unittest.mock import patch, MagicMock
import httpx

from apps.platform.services.docs_search import fetch_docs_search, federated_search

class DocsSearchTest(SimpleTestCase):

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_empty_query(self, mock_get):
        # Test completely empty strings and None
        self.assertEqual(fetch_docs_search(""), [])
        self.assertEqual(fetch_docs_search(None), [])
        mock_get.assert_not_called()

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_success_match_title(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "documents": [
                {"id": 1, "title": "How to deploy", "content": "Deployment guide", "route": "/docs/deploy"},
                {"id": 2, "title": "Other", "content": "Unrelated", "route": "/docs/other"}
            ]
        }
        mock_get.return_value = mock_response

        # Case-insensitive match on title
        results = fetch_docs_search("DEPLOY")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(results[0]["title"], "How to deploy")
        self.assertEqual(results[0]["url"], "/docs/deploy")
        self.assertEqual(results[0]["snippet"], "Deployment guide...")
        mock_get.assert_called_once_with("http://localhost:3000/search-doc.json", timeout=3.0)

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_success_match_content(self, mock_get):
        mock_response = MagicMock()
        long_content = "This is a very long content string that exceeds one hundred and fifty characters in length to ensure that the truncation behavior works exactly as expected when the slice is applied."
        mock_response.json.return_value = {
            "documents": [
                {"id": 3, "title": "Short title", "content": long_content, "route": "/docs/long"}
            ]
        }
        mock_get.return_value = mock_response

        # Match on content
        results = fetch_docs_search("exceeds one hundred")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], 3)
        self.assertTrue(results[0]["snippet"].endswith("..."))
        self.assertEqual(len(results[0]["snippet"]), 150 + 3) # 150 chars + "..."

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_missing_fields(self, mock_get):
        # Test documents that are missing expected keys
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "documents": [
                {"content": "Match this content"} # Missing id, title, route
            ]
        }
        mock_get.return_value = mock_response

        results = fetch_docs_search("match")
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0]["id"])
        self.assertIsNone(results[0]["title"])
        self.assertEqual(results[0]["url"], "")
        self.assertEqual(results[0]["snippet"], "Match this content...")

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_http_error(self, mock_get):
        # Test HTTP Status error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=MagicMock())
        mock_get.return_value = mock_response

        with self.assertLogs("apps.platform.services.docs_search", level="ERROR") as cm:
            results = fetch_docs_search("test")
        
        self.assertEqual(results, [])
        self.assertTrue(any("Failed to fetch or search docs index" in log for log in cm.output))

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_network_error(self, mock_get):
        # Test connection/timeout error
        mock_get.side_effect = httpx.RequestError("Connection timeout")

        with self.assertLogs("apps.platform.services.docs_search", level="ERROR") as cm:
            results = fetch_docs_search("test")
            
        self.assertEqual(results, [])
        self.assertTrue(any("Failed to fetch or search docs index" in log for log in cm.output))

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_malformed_json(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        results = fetch_docs_search("test")
        self.assertEqual(results, [])

    @patch("apps.platform.services.docs_search.httpx.get")
    def test_fetch_docs_search_no_documents_key(self, mock_get):
        # JSON parsed successfully but has no "documents" key
        mock_response = MagicMock()
        mock_response.json.return_value = {"other_key": []}
        mock_get.return_value = mock_response

        results = fetch_docs_search("test")
        self.assertEqual(results, [])

    @patch("apps.platform.services.docs_search.fetch_docs_search")
    def test_federated_search(self, mock_fetch):
        mock_fetch.return_value = [{"id": 1, "title": "Doc Result", "url": "/docs", "snippet": "..."}]
        results = federated_search("test query")
        
        mock_fetch.assert_called_once_with("test query")
        self.assertIn("internal_results", results)
        self.assertIn("documentation_results", results)
        self.assertEqual(len(results["documentation_results"]), 1)
        self.assertEqual(results["documentation_results"][0]["title"], "Doc Result")
        self.assertEqual(results["internal_results"], [])
