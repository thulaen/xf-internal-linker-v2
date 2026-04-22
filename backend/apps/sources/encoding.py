"""Character-encoding detection for incoming HTTP response bodies.

Reference: Li & Momoi (2001) "A Composite Approach to Language and
Encoding Detection" (18th Unicode Conference) — the original chardet
algorithm. Modern Python projects typically use either ``chardet``
or ``charset-normalizer``; this module prefers ``charset-normalizer``
(it's already a transitive dep of ``requests``) and falls back to a
conservative stdlib-only heuristic when the library is not importable.

Detection order (first wins):

1. **HTTP ``Content-Type`` header.** When present, the ``charset=``
   parameter is authoritative per RFC 9110 §8.3.1. The declared
   encoding might still be wrong (misconfigured servers happen) but
   trusting it first matches what every real HTTP client does.

2. **HTML ``<meta>`` charset in the first ~4 kB of the body.** HTML5
   §8.2.2.2 says clients should honour the BOM, then ``Content-Type``
   header, then ``<meta http-equiv>`` or ``<meta charset>``. We scan
   a short window because a charset declared past 4 kB is not
   compliant and rarely appears in practice.

3. **Byte-order mark (BOM).** UTF-8/UTF-16-LE/UTF-16-BE/UTF-32-LE/
   UTF-32-BE signatures unambiguously identify the encoding.

4. **charset-normalizer library** (if importable). Statistical
   multi-hypothesis classifier — the best pure-detection tool in
   the stdlib ecosystem.

5. **Stdlib fallback.** Try ``utf-8`` strict. If that works the bytes
   are unambiguously UTF-8. Otherwise fall back to ``latin-1`` —
   it's byte-to-codepoint bijective so it never raises, which is
   what every pragmatic "just give me a string" client does.

All functions are dependency-free at import time; the
``charset-normalizer`` import happens inside :func:`detect_encoding`
only when it's actually reached. That keeps the module's load cost
zero on call paths that already know their encoding.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Max bytes scanned for a ``<meta charset=>`` declaration.
_META_SCAN_WINDOW: int = 4096

#: BOM signatures — longest first so UTF-32 wins over UTF-16 bit-patterns.
_BOM_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xff\xfe", "utf-16-le"),
)

#: Regex for the HTML5 ``<meta charset=X>`` and the legacy
#: ``<meta http-equiv="Content-Type" content="... charset=X">`` syntax.
#: Matched ASCII-insensitively on byte strings so we don't need to
#: decode before we know the encoding.
_META_CHARSET_RE = re.compile(
    rb"<meta\s+[^>]*?charset\s*=\s*[\"']?([A-Za-z0-9_\-:]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EncodingGuess:
    """Outcome of :func:`detect_encoding`.

    Source codes:
      - ``"header"``     — trusted the ``Content-Type`` charset param
      - ``"meta"``       — parsed ``<meta charset>`` out of the body
      - ``"bom"``        — BOM signature match
      - ``"normalizer"`` — delegated to ``charset-normalizer``
      - ``"utf-8"``      — body decoded clean as UTF-8
      - ``"latin-1"``    — bijective fallback; encoding genuinely
                           unknown but body is still decodable
      - ``"empty"``      — zero-byte body; chose ``utf-8`` by default
    """

    encoding: str
    source: str
    confidence: float  # 0.0–1.0; header/bom/meta are 1.0


def parse_content_type_charset(content_type: str | None) -> str | None:
    """Extract the ``charset=X`` parameter from a ``Content-Type`` header.

    Returns ``None`` when the header is missing, empty, or does not
    declare a charset. Spaces, mixed case, and double-quoted values are
    all tolerated.
    """
    if not content_type:
        return None
    # RFC 9110 §8.3.1 parameter form: ``type/subtype; charset=X``.
    # We look for ``charset=`` case-insensitively and pull the value
    # up to the next ``;`` or end-of-string.
    match = re.search(
        r"charset\s*=\s*\"?([A-Za-z0-9_\-:]+)\"?",
        content_type,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).strip()


def _detect_from_bom(body: bytes) -> str | None:
    for signature, encoding in _BOM_SIGNATURES:
        if body.startswith(signature):
            return encoding
    return None


def _detect_from_meta(body: bytes) -> str | None:
    window = body[:_META_SCAN_WINDOW]
    match = _META_CHARSET_RE.search(window)
    if not match:
        return None
    try:
        return match.group(1).decode("ascii", errors="ignore").strip()
    except UnicodeDecodeError:
        return None


def _detect_with_normalizer(body: bytes) -> tuple[str, float] | None:
    """Delegate to ``charset-normalizer`` if installed. Returns None on any error."""
    try:
        import charset_normalizer  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        result = charset_normalizer.from_bytes(body).best()
    except Exception:  # noqa: BLE001 — never crash on library internals
        logger.debug("encoding: charset_normalizer raised — falling through")
        return None
    if result is None:
        return None
    encoding = str(result.encoding).lower()
    # charset-normalizer reports chaos in [0, 1]; invert to "confidence".
    chaos = getattr(result, "chaos", 0.0)
    confidence = max(0.0, min(1.0, 1.0 - float(chaos)))
    return encoding, confidence


def _stdlib_utf8_or_latin1(body: bytes) -> EncodingGuess:
    """Strictest-wins fallback: try UTF-8, else latin-1 (bijective)."""
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return EncodingGuess(encoding="latin-1", source="latin-1", confidence=0.4)
    return EncodingGuess(encoding="utf-8", source="utf-8", confidence=0.9)


def detect_encoding(
    body: bytes,
    *,
    content_type: str | None = None,
) -> EncodingGuess:
    """Return the best-guess encoding for *body*.

    ``body`` is the raw response bytes. ``content_type`` is the HTTP
    ``Content-Type`` header value (e.g. ``"text/html; charset=UTF-8"``)
    if available.

    Never raises. Worst case returns ``latin-1`` with low confidence.
    """
    if not body:
        return EncodingGuess(encoding="utf-8", source="empty", confidence=1.0)

    # Tier 1: HTTP Content-Type header.
    header_charset = parse_content_type_charset(content_type)
    if header_charset:
        return EncodingGuess(
            encoding=header_charset.lower(),
            source="header",
            confidence=1.0,
        )

    # Tier 2: in-body <meta charset=...>.
    meta_charset = _detect_from_meta(body)
    if meta_charset:
        return EncodingGuess(
            encoding=meta_charset.lower(),
            source="meta",
            confidence=1.0,
        )

    # Tier 3: BOM.
    bom_charset = _detect_from_bom(body)
    if bom_charset:
        return EncodingGuess(
            encoding=bom_charset,
            source="bom",
            confidence=1.0,
        )

    # Tier 4: charset-normalizer (if installed).
    normalizer_result = _detect_with_normalizer(body)
    if normalizer_result is not None:
        encoding, confidence = normalizer_result
        return EncodingGuess(
            encoding=encoding,
            source="normalizer",
            confidence=confidence,
        )

    # Tier 5: stdlib UTF-8 strict → latin-1 fallback.
    return _stdlib_utf8_or_latin1(body)


def decode_with_guess(
    body: bytes,
    *,
    content_type: str | None = None,
) -> tuple[str, EncodingGuess]:
    """Decode *body* using the detected encoding. Returns (text, guess).

    The decode uses ``errors="replace"`` so the result is always a
    valid ``str``, even if the guess was wrong — you get U+FFFD
    replacement characters where bytes didn't match the guess. That's
    preferable to raising, because the crawler is better off storing
    an imperfect body than discarding the page entirely.
    """
    guess = detect_encoding(body, content_type=content_type)
    try:
        text = body.decode(guess.encoding, errors="replace")
    except LookupError:
        # Obscure / made-up encoding name — fall back to latin-1 which
        # accepts anything.
        logger.warning(
            "encoding: unknown charset %r declared by %s — falling back to latin-1",
            guess.encoding,
            guess.source,
        )
        text = body.decode("latin-1", errors="replace")
        guess = EncodingGuess(
            encoding="latin-1",
            source=f"{guess.source}→latin-1",
            confidence=0.3,
        )
    return text, guess
