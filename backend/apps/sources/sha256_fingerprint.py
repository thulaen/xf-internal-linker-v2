"""SHA-256 page-content fingerprint — pick #12.

Reference
---------
National Institute of Standards and Technology (August 2015).
*FIPS 180-4: Secure Hash Standard.*
<https://csrc.nist.gov/publications/fips/fips180-4/fips-180-4.pdf>

Why this exists
---------------
The crawler used to inline ``hashlib.sha256(text.encode()).hexdigest()``
at the parse boundary. Two problems with the inline approach:

1. **Canonical-equivalence gotcha.** ``"café"`` (precomposed
   ``U+00E9``) and ``"café"`` (e + combining acute ``U+0301``) hash
   to different digests even though they're the same word. NFKC
   normalisation before hashing is the fix — pick spec §13's stated
   caveat.
2. **No read-side dedup utility.** Callers wanting "have I already
   embedded a row with this content hash?" had to hand-roll the
   query each time.

This module owns both concerns: a single hashing function used by the
crawler + import paths, and a tiny lookup helper the embed pipeline
can call before scheduling a (potentially redundant) GPU embed.
"""

from __future__ import annotations

import hashlib
import logging

from .normalize import nfkc

logger = logging.getLogger(__name__)


#: Below this many characters of cleaned text the hash is over a
#: trivial body (an empty placeholder, an error page) and dedup on
#: it produces false collapses. Pick spec §6 default.
MIN_TEXT_CHARS_FOR_HASH: int = 50


def fingerprint(text: str | None) -> str | None:
    """Return the SHA-256 hex digest of NFKC-normalised *text*.

    Empty or short input returns ``None``: the caller treats that as
    "this row isn't a candidate for content-level dedup" rather than
    paying for a pointless hash.
    """
    if not text:
        return None
    if len(text) < MIN_TEXT_CHARS_FOR_HASH:
        return None
    canonical = nfkc(text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_bytes(data: bytes | None) -> str | None:
    """Return the SHA-256 hex digest of raw bytes.

    For non-text content (PDFs, binary files) where decoding +
    NFKC don't apply. Empty input returns ``None``.
    """
    if not data:
        return None
    return hashlib.sha256(data).hexdigest()


# ── Read-side dedup ───────────────────────────────────────────────


def find_duplicate_content_hash(
    content_hash: str | None,
    *,
    exclude_pk: int | None = None,
) -> int | None:
    """Return the primary key of an existing :class:`CrawledPageMeta`
    row with the same ``content_hash``, or ``None`` if no duplicate
    exists.

    Use this from the embed pipeline as::

        existing_pk = find_duplicate_content_hash(meta.content_hash,
                                                  exclude_pk=meta.pk)
        if existing_pk is not None:
            copy_embedding_from(existing_pk)  # skip GPU work
            return

    Callers expecting many rows per hash (e.g. a content-survey
    audit) should use the ORM directly. This helper is optimised for
    the "skip the embed" hot path — it returns the first match and
    bails.

    Returns ``None`` if ``content_hash`` itself is falsy.
    """
    if not content_hash:
        return None
    try:
        from apps.crawler.models import CrawledPageMeta

        qs = CrawledPageMeta.objects.filter(content_hash=content_hash)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        match = qs.values_list("pk", flat=True).first()
        return int(match) if match is not None else None
    except Exception:
        # The dedup hook is opt-in and best-effort. A DB hiccup
        # mustn't block ingestion — log and let the caller proceed
        # with a fresh embed.
        logger.debug(
            "find_duplicate_content_hash: lookup failed for %s",
            content_hash,
            exc_info=True,
        )
        return None
