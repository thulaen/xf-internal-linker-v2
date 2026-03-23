"""
Anchor extractor service — extracts and validates anchor text for suggestions.

Enforces anchor text policy:
- Prefer long-tail anchors (3+ words)
- Allow 1–2 word anchors when they are specific
- Ban generic anchors: "click here", "read more", "this post", etc.
- Cap exact-match anchor reuse across the forum

Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/anchor_extractor.py
"""

# Generic anchors that are never allowed
BANNED_ANCHORS = {
    "click here",
    "read more",
    "this post",
    "this thread",
    "here",
    "link",
    "more",
    "see more",
    "learn more",
    "visit",
    "go here",
}

# TODO Phase 2: migrate from V1 anchor_extractor.py


def extract_anchor(sentence: str, destination_title: str) -> str | None:
    """
    Extract the best anchor text for a link suggestion.

    Args:
        sentence: The host sentence where the link would be inserted.
        destination_title: The title of the destination thread.

    Returns:
        The suggested anchor text, or None if no valid anchor found.

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Anchor extractor service migrated in Phase 2")


def is_anchor_banned(anchor: str) -> bool:
    """
    Check if an anchor text is on the banned list.

    Args:
        anchor: The anchor text to check (case-insensitive).

    Returns:
        True if the anchor is banned and should not be used.
    """
    return anchor.lower().strip() in BANNED_ANCHORS
