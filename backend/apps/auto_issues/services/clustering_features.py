"""Feature-hash extraction for root-cause clustering.

Turns an issue's text + affected paths into a set of 64-bit feature hashes —
k-shingles of the normalised template plus the affected-path set — matching the
Rust ``cluster_core`` contract (a list of ``u64`` per item). Normalisation masks
the variable parts (numbers, hex, UUIDs, paths) so two issues that differ only
in an id or line number share features, mirroring the ``canonical_fingerprint``
notion of "the same underlying problem".

Pure and deterministic (stdlib + hashlib only) so it is trivially testable and
gives identical features across processes.
"""
from __future__ import annotations

import hashlib
import re
from typing import List, Sequence

# Mask hex pointers, long hex blobs, unix-ish paths, and 2+ digit runs.
_NORMALIZE = re.compile(r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8,}|/[\w./-]+|\d{2,}")
_TOKEN = re.compile(r"[a-z0-9]+")
DEFAULT_K = 5
_MASK64 = (1 << 64) - 1


def normalize(text: str) -> str:
    """Lowercase and mask variable substrings with ``*``."""
    return _NORMALIZE.sub("*", (text or "").lower())


def _hash64(text: str) -> int:
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & _MASK64


def feature_hashes(
    title: str,
    body: str = "",
    paths: Sequence[str] = (),
    k: int = DEFAULT_K,
) -> List[int]:
    """Return the sorted set of 64-bit feature hashes for one issue.

    Features = k-shingles of the normalised ``title + body`` token stream, plus
    one hash per affected path. Sorted + de-duplicated for determinism.
    """
    tokens = _TOKEN.findall(normalize(f"{title} {body}"))
    features = set()
    if len(tokens) >= k:
        for i in range(len(tokens) - k + 1):
            features.add(_hash64(" ".join(tokens[i : i + k])))
    elif tokens:
        # Shorter than one shingle: hash the whole (normalised) token stream.
        features.add(_hash64(" ".join(tokens)))
    for path in paths or ():
        features.add(_hash64("path:" + normalize(path)))
    return sorted(features)
