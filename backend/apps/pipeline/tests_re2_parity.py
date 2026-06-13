"""Parity suite: the RE2 link-parser patterns match stdlib `re` exactly.

The five link-parser patterns were moved from `re` to RE2 (google-re2) so a
crafted forum post can't trigger catastrophic backtracking. RE2 is a different
engine, so this permanent regression suite proves the swap did not change WHAT
the patterns match — only how fast they fail on hostile input. For every
fixture (ordinary content plus adversarial inputs) the RE2 result must equal
the stdlib-`re` result for the identical pattern string.
"""

from __future__ import annotations

import re

from django.test import SimpleTestCase

from apps.pipeline.services import link_parser

# (production RE2 pattern, identical pattern string for stdlib `re`). The
# pattern strings carry inline flags ((?i)/(?is)) so the SAME text compiles
# under both engines — the truest parity check.
_PATTERNS = [
    (link_parser._XF_THREAD_RE, r"(?i)/threads/(?:[^/]*\.)?(\d+)(?:/|$)"),
    (link_parser._XF_RESOURCE_RE, r"(?i)/resources/(?:[^/]*\.)?(\d+)(?:/|$)"),
    (link_parser._BBCODE_URL_RE, r"(?is)\[URL=([^\]]+)\](.*?)\[/URL\]"),
    (link_parser._HTML_LINK_RE, r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>"),
    (link_parser._CONTEXT_TOKEN_RE, r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?"),
]

_FIXTURES = [
    "",
    "/threads/some-slug.12345/",
    "/threads/12345",
    "/resources/cool-addon.99/download",
    "no link here at all",
    "[URL=https://forum.example.com/threads/cool.7/]click me[/URL]",
    "[url=/threads/9/]Mixed Case[/URL] trailing",
    '<a href="https://x.test/threads/3/">anchor</a> tail',
    "<a class='c' href='/resources/2/'>res</a>",
    "word can't stop won't stop 2nd-place",
    # adversarial: long repetition that catastrophically backtracks naive engines
    "[URL=" + "a" * 5000 + "]" + "b" * 5000,
    "<a " + "x" * 5000 + " href=",
    "/threads/" + "9" * 4000,
    "." * 3000 + "!?",
]


def _search_groups(pattern, text):
    m = pattern.search(text)
    return None if m is None else m.groups()


def _finditer_groups(pattern, text):
    return [m.groups() for m in pattern.finditer(text)]


class Re2ParityTests(SimpleTestCase):
    def test_search_results_match_stdlib_re(self) -> None:
        for re2_pat, src in _PATTERNS:
            re_pat = re.compile(src)
            for text in _FIXTURES:
                self.assertEqual(
                    _search_groups(re2_pat, text),
                    _search_groups(re_pat, text),
                    msg=f"search mismatch for {src!r} on {text[:40]!r}",
                )

    def test_finditer_results_match_stdlib_re(self) -> None:
        for re2_pat, src in _PATTERNS:
            re_pat = re.compile(src)
            for text in _FIXTURES:
                self.assertEqual(
                    _finditer_groups(re2_pat, text),
                    _finditer_groups(re_pat, text),
                    msg=f"finditer mismatch for {src!r} on {text[:40]!r}",
                )

    def test_patterns_are_re2_not_stdlib(self) -> None:
        # Guard against a silent revert to `re`: the production objects must be
        # RE2 compiled patterns, which expose a distinct type from re.Pattern.
        self.assertNotIsInstance(link_parser._HTML_LINK_RE, re.Pattern)
        self.assertNotIsInstance(link_parser._BBCODE_URL_RE, re.Pattern)
