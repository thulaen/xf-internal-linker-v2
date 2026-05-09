"""Tests for ``apps.sync.services.xenforo_search``.

Pure ``SimpleTestCase`` — no DB, no Docker, no live HTTP. Every test
mocks the underlying ``XenForoAPIClient._get`` so the search client is
exercised in isolation. The HTTP shapes mirror what XF 2.x with the
Enhanced Search add-on actually returns; the parser is also exercised
against the flatter shapes some XF forks emit.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.sync.services.xenforo_search import (
    XenForoSearchClient,
    XFSearchHit,
    _coerce_float,
    _coerce_int,
    _infer_type,
    _pick_content_id,
)


def _make_client(get_return_value=None, get_side_effect=None) -> XenForoSearchClient:
    """Construct a search client with a mocked-out ``_get``.

    Avoids touching ``XENFORO_BASE_URL`` / ``XENFORO_API_KEY`` settings
    by injecting a pre-built ``XenForoAPIClient`` whose ``_get`` is a
    plain ``Mock``.
    """
    fake_client = Mock()
    fake_client.base_url = "https://forum.example.com"
    if get_side_effect is not None:
        fake_client._get = Mock(side_effect=get_side_effect)
    else:
        fake_client._get = Mock(return_value=get_return_value or {"results": []})
    return XenForoSearchClient(client=fake_client)


# ── Helper unit tests ────────────────────────────────────────────────


class CoerceHelpersTests(SimpleTestCase):
    def test_coerce_int_returns_none_on_failure(self) -> None:
        self.assertIsNone(_coerce_int(None))
        self.assertIsNone(_coerce_int("abc"))
        self.assertIsNone(_coerce_int({}))

    def test_coerce_int_parses_valid_inputs(self) -> None:
        self.assertEqual(_coerce_int(42), 42)
        self.assertEqual(_coerce_int("17"), 17)
        self.assertEqual(_coerce_int(3.9), 3)  # truncation matches int()

    def test_coerce_float_falls_back_to_zero(self) -> None:
        self.assertEqual(_coerce_float(None), 0.0)
        self.assertEqual(_coerce_float("not-a-number"), 0.0)
        self.assertEqual(_coerce_float("2.5"), 2.5)
        self.assertEqual(_coerce_float(7), 7.0)

    def test_infer_type_picks_id_field(self) -> None:
        self.assertEqual(_infer_type({"thread_id": 1}), "thread")
        self.assertEqual(_infer_type({"post_id": 1}), "post")
        self.assertEqual(
            _infer_type({"thread_id": 1, "post_id": 2}), "post"
        )  # post wins when both present
        self.assertEqual(_infer_type({"resource_id": 1}), "resource")
        self.assertEqual(_infer_type({}), "")

    def test_pick_content_id_prefers_type_specific_field(self) -> None:
        self.assertEqual(
            _pick_content_id({"thread_id": 7, "content_id": 99}, "thread"), 7
        )
        self.assertEqual(
            _pick_content_id({"post_id": 7, "content_id": 99}, "post"), 7
        )
        self.assertEqual(
            _pick_content_id({"resource_id": 7, "content_id": 99}, "resource"), 7
        )
        # Unknown type falls back to content_id
        self.assertEqual(_pick_content_id({"content_id": 99}, "wat"), 99)
        # Falls back to content_id when type-specific field missing
        self.assertEqual(_pick_content_id({"content_id": 5}, "thread"), 5)


# ── Search client tests ──────────────────────────────────────────────


class SearchThreadsTests(SimpleTestCase):
    def test_returns_parsed_hits_from_xf_2x_payload(self) -> None:
        payload = {
            "results": [
                {
                    "content_type": "thread",
                    "content": {
                        "thread_id": 101,
                        "title": "How to fix bug X",
                        "snippet": "...we found <em>bug X</em> stems from...",
                        "score": 12.5,
                    },
                },
                {
                    "content_type": "thread",
                    "content": {
                        "thread_id": 202,
                        "title": "Bug X workaround",
                        "snippet": "Workaround for <em>bug X</em>",
                        "score": 9.8,
                    },
                },
            ]
        }
        client = _make_client(get_return_value=payload)

        hits = client.search_threads("bug X", limit=10)

        self.assertEqual(len(hits), 2)
        self.assertEqual(
            hits[0],
            XFSearchHit(
                content_id=101,
                content_type="thread",
                title="How to fix bug X",
                snippet="...we found <em>bug X</em> stems from...",
                score=12.5,
                raw=payload["results"][0],
            ),
        )
        self.assertEqual(hits[1].content_id, 202)
        client._client._get.assert_called_once_with(  # noqa: SLF001 — verifying the call
            "search/", params={"q": "bug X", "search_type": "thread", "limit": 10}
        )

    def test_blank_query_short_circuits_without_http(self) -> None:
        client = _make_client(get_return_value={"results": []})
        self.assertEqual(client.search_threads("   "), [])
        client._client._get.assert_not_called()  # noqa: SLF001

    def test_zero_limit_short_circuits_without_http(self) -> None:
        client = _make_client(get_return_value={"results": []})
        self.assertEqual(client.search_threads("foo", limit=0), [])
        self.assertEqual(client.search_threads("foo", limit=-5), [])
        client._client._get.assert_not_called()  # noqa: SLF001

    def test_http_failure_returns_empty_list_and_logs(self) -> None:
        client = _make_client(get_side_effect=RuntimeError("network down"))
        with patch("apps.sync.services.xenforo_search.logger") as mock_logger:
            hits = client.search_threads("anything")
        self.assertEqual(hits, [])
        mock_logger.warning.assert_called_once()


class SearchPostsTests(SimpleTestCase):
    def test_returns_parsed_post_hits(self) -> None:
        payload = {
            "results": [
                {
                    "content_type": "post",
                    "content": {
                        "post_id": 555,
                        "thread_id": 101,
                        "title": "Re: How to fix bug X",
                        "snippet": "I had the same problem with <em>bug X</em>",
                        "score": 7.1,
                    },
                }
            ]
        }
        client = _make_client(get_return_value=payload)
        hits = client.search_posts("bug X")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].content_id, 555)
        self.assertEqual(hits[0].content_type, "post")
        client._client._get.assert_called_once_with(  # noqa: SLF001
            "search/", params={"q": "bug X", "search_type": "post", "limit": 200}
        )


class MoreLikePostTests(SimpleTestCase):
    def test_passes_more_like_param(self) -> None:
        client = _make_client(get_return_value={"results": []})
        client.more_like_post(42, limit=15)
        client._client._get.assert_called_once_with(  # noqa: SLF001
            "search/", params={"more_like": 42, "limit": 15}
        )


class ParsingEdgeCasesTests(SimpleTestCase):
    def test_results_not_a_list_returns_empty(self) -> None:
        client = _make_client(get_return_value={"results": "oops"})
        self.assertEqual(client.search_threads("foo"), [])

    def test_results_missing_returns_empty(self) -> None:
        client = _make_client(get_return_value={})
        self.assertEqual(client.search_threads("foo"), [])

    def test_hit_with_missing_content_id_is_dropped(self) -> None:
        payload = {
            "results": [
                {"content_type": "thread", "content": {"title": "no id"}},
                {"content_type": "thread", "content": {"thread_id": 99, "title": "ok"}},
            ]
        }
        client = _make_client(get_return_value=payload)
        hits = client.search_threads("anything")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].content_id, 99)

    def test_flat_payload_shape_is_supported(self) -> None:
        """Some XF forks return flat hits without the ``content`` nesting."""
        payload = {
            "results": [
                {
                    "content_type": "thread",
                    "thread_id": 7,
                    "title": "flat hit",
                    "score": 1.0,
                }
            ]
        }
        client = _make_client(get_return_value=payload)
        hits = client.search_threads("foo")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].content_id, 7)
        self.assertEqual(hits[0].title, "flat hit")

    def test_inferred_type_when_xf_omits_content_type(self) -> None:
        payload = {
            "results": [
                {"content": {"thread_id": 11, "title": "guessable thread"}},
            ]
        }
        client = _make_client(get_return_value=payload)
        hits = client.search_threads("foo")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].content_type, "thread")
        self.assertEqual(hits[0].content_id, 11)
