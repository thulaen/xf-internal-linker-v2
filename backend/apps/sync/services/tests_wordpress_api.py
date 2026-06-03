"""Convention-named SimpleTestCase coverage for sync/services/wordpress_api.py.

Issue #2027: ``verify_credentials`` previously called ``resp.json()`` directly.
When WordPress returned an empty or non-JSON body on a transient error, the
raw ``json.JSONDecodeError`` (a ``ValueError`` subclass) bubbled up and the
whole credentials probe crashed.  The method now wraps the parse in a
try/except and returns ``{"ok": False, "display_name": ""}`` on any parse
failure, and guards ``display_name`` with ``isinstance(data, dict)`` so a JSON
list/scalar body does not raise ``AttributeError`` either.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.sync.services.wordpress_api import WordPressAPIClient


class VerifyCredentialsParseGuardTests(SimpleTestCase):
    def _make_client(self) -> WordPressAPIClient:
        return WordPressAPIClient(
            base_url="https://blog.example.com",
            username="editor",
            app_password="app-pass",
        )

    def _response(self, *, json_value=None, json_exc=None) -> Mock:
        resp = Mock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        if json_exc is not None:
            resp.json.side_effect = json_exc
        else:
            resp.json.return_value = json_value
        return resp

    def test_empty_body_returns_ok_false(self) -> None:
        """An empty body raises JSONDecodeError; the probe must not crash."""
        client = self._make_client()
        client.session.get = Mock(
            return_value=self._response(json_exc=ValueError("Expecting value"))
        )
        with patch("apps.sync.services.wordpress_api.rate_limited"):
            result = client.verify_credentials()
        self.assertEqual(result, {"ok": False, "display_name": ""})

    def test_non_dict_json_body_does_not_crash(self) -> None:
        """A JSON list body must not raise AttributeError on data.get()."""
        client = self._make_client()
        client.session.get = Mock(return_value=self._response(json_value=[1, 2, 3]))
        with patch("apps.sync.services.wordpress_api.rate_limited"):
            result = client.verify_credentials()
        self.assertEqual(result, {"ok": True, "display_name": ""})

    def test_valid_json_returns_display_name(self) -> None:
        """A normal object body still returns ok=True with the display name."""
        client = self._make_client()
        client.session.get = Mock(
            return_value=self._response(json_value={"name": "Alice"})
        )
        with patch("apps.sync.services.wordpress_api.rate_limited"):
            result = client.verify_credentials()
        self.assertEqual(result, {"ok": True, "display_name": "Alice"})

    def test_dict_without_name_key_returns_empty_default(self) -> None:
        """A dict body missing ``name`` must return the exact ``""`` default.

        Pins the ``data.get("name", "")`` default so a literal mutant on the
        empty-string default (``""`` -> ``"XX"``) is killed.
        """
        client = self._make_client()
        client.session.get = Mock(
            return_value=self._response(json_value={"id": 7, "slug": "alice"})
        )
        with patch("apps.sync.services.wordpress_api.rate_limited"):
            result = client.verify_credentials()
        self.assertEqual(result, {"ok": True, "display_name": ""})

    def test_401_returns_ok_false_exact_shape(self) -> None:
        """HTTP 401 returns the exact failure dict before any JSON parse.

        Pins the early-return branch and its exact ``""`` display name so a
        literal mutant on that string is killed independently of the parse path.
        """
        client = self._make_client()
        resp = Mock()
        resp.status_code = 401
        client.session.get = Mock(return_value=resp)
        with patch("apps.sync.services.wordpress_api.rate_limited"):
            result = client.verify_credentials()
        self.assertEqual(result, {"ok": False, "display_name": ""})
