"""
Link parser service — BBCode link extraction from XenForo posts.

Parses existing links in a thread to:
- Detect already-linked destinations (avoid duplicate suggestions)
- Build the link graph for PageRank computation
- Track anchor text reuse

Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/link_parser.py
"""

import re
from typing import NamedTuple

# BBCode URL patterns
BBCODE_URL_RE = re.compile(r"\[url(?:=([^\]]+))?\](.*?)\[/url\]", re.IGNORECASE | re.DOTALL)
BBCODE_PLAIN_URL_RE = re.compile(r"\[url\](https?://[^\[]+)\[/url\]", re.IGNORECASE)


class ParsedLink(NamedTuple):
    """A link found in BBCode content."""

    url: str
    anchor_text: str


def extract_links(bbcode_content: str) -> list[ParsedLink]:
    """
    Extract all links from XenForo BBCode content.

    Args:
        bbcode_content: Raw BBCode string from a XenForo post.

    Returns:
        List of ParsedLink(url, anchor_text) named tuples.

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Link parser service migrated in Phase 2")
