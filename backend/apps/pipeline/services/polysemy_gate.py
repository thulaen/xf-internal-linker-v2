"""FR-243 — Polysemy detection gate for host sentences.

Detects host sentences whose tokens have multiple WordNet senses (e.g.
"Apple" the company vs "apple" the fruit) and emits a diagnostic so
operators can see when polysemy is in play. The full LMMS sense-vector
disambiguation (Loureiro & Jorge 2019) is documented but not yet
implemented — the v1 scaffold ships the *detector* + diagnostic so
operators have visibility into the failure mode while the heavier
sense-vector picker is built.

Sources of truth:
    * Loureiro, D. & Jorge, A. (2019). *Language Modelling Makes Sense:
      Propagating Representations through WordNet for Full-Coverage
      Word Sense Disambiguation* (LMMS). ACL. arXiv:1906.10007. Defines
      sense-vector embeddings compatible with sentence encoders.
    * Bevilacqua, M. et al. (2021). *Recent Trends in Word Sense
      Disambiguation: A Survey.* IJCAI. Survey of viable approaches.
      §2.1 — minimum 2 WordNet senses to consider a word polysemous.
    * Miller, G. A. (1995). *WordNet: A Lexical Database for English.*
      CACM 38(11). https://wordnet.princeton.edu/. The lexical
      database we query for sense counts.

Default state: ON (detector). Returns empty list when WordNet is not
installed (typical Docker container), so the path is safe and free.
The wire-in into the retrieval pipeline is deferred until the LMMS
sense-vector picker is implemented; today the scaffold only emits
diagnostics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Bevilacqua 2021 §2.1 — minimum 2 distinct senses to call a word
# polysemous. 1-sense words are not ambiguous.
MIN_POLYSEMY_THRESHOLD: int = 2

# Loureiro 2019 §4.2 — sense-separation cosine floor below which two
# senses are considered "the same meaning" (used by the v2 LMMS picker).
TOPICAL_CLUSTER_MIN_DISTANCE: float = 0.3


@dataclass(frozen=True, slots=True)
class PolysemyDiagnostic:
    """Per-sentence diagnostic emitted by ``gate_polysemy``.

    ``polysemous_terms`` is the list of surface forms that have ≥2
    WordNet senses. ``runtime_path`` says whether WordNet was actually
    queried or whether the no-NLTK fallback was used. Operators see
    this on the diagnostics view.
    """

    polysemous_terms: tuple[str, ...]
    runtime_path: str
    runtime_reason: str


def _try_import_wordnet():
    """Return the NLTK WordNet corpus if importable; else ``None``."""
    try:
        from nltk.corpus import wordnet  # type: ignore[import-not-found]

        # Access a synset to force the corpus download check at import time.
        _ = wordnet.synsets("apple")
        return wordnet
    except Exception:  # noqa: BLE001 — any failure → no-WordNet fallback.
        return None


def _count_senses(wordnet, term: str) -> int:
    """Count WordNet synsets for *term*. Returns 0 on lookup failure."""
    try:
        return len(wordnet.synsets(term))
    except Exception:  # noqa: BLE001 — defensive: bad input → 0 senses.
        return 0


def detect_polysemous_terms(
    text: str,
    *,
    min_polysemy: int = MIN_POLYSEMY_THRESHOLD,
    wordnet_module: Optional[object] = None,
) -> list[str]:
    """Return the list of surface forms in *text* with ≥ ``min_polysemy`` senses.

    Bevilacqua 2021 §2.1 — surface forms with multiple WordNet senses
    are the operative definition of polysemy. Tokens not in WordNet
    (proper nouns, neologisms, brand names) return 0 senses and are
    excluded — they're handled by FR-242 domain adapter, not here.

    ``wordnet_module`` is an optional injected module for tests. When
    omitted, the function tries to import NLTK's WordNet at call time;
    if NLTK is unavailable, returns an empty list (cold-start safe).
    """
    if not text:
        return []
    wordnet = wordnet_module if wordnet_module is not None else _try_import_wordnet()
    if wordnet is None:
        return []
    # Lightweight tokenization — split on whitespace, lowercase.
    # Avoids the heavier text_tokens pipeline because polysemy
    # detection is per-token, not per-document.
    tokens = {raw.strip(".,!?:;\"'()[]{}").lower() for raw in text.split()}
    tokens = {t for t in tokens if t and len(t) >= 2}
    out: list[str] = []
    for token in sorted(tokens):
        if _count_senses(wordnet, token) >= min_polysemy:
            out.append(token)
    return out


def gate_polysemy(
    host_sentence: str,
    *,
    min_polysemy: int = MIN_POLYSEMY_THRESHOLD,
    wordnet_module: Optional[object] = None,
) -> PolysemyDiagnostic:
    """Return the polysemy diagnostic for a host sentence.

    The diagnostic is intended to be attached to the per-sentence
    output (eventually wired into ``SentenceSemanticMatch.diagnostics``)
    so operators can filter / sort by polysemy hits in the review UI.
    """
    wordnet = wordnet_module if wordnet_module is not None else _try_import_wordnet()
    if wordnet is None:
        return PolysemyDiagnostic(
            polysemous_terms=(),
            runtime_path="no_wordnet",
            runtime_reason=(
                "WordNet (NLTK) not available in this environment. "
                "Polysemy gating is a no-op; install nltk + the WordNet "
                "corpus to enable detection."
            ),
        )
    terms = detect_polysemous_terms(
        host_sentence, min_polysemy=min_polysemy, wordnet_module=wordnet
    )
    return PolysemyDiagnostic(
        polysemous_terms=tuple(terms),
        runtime_path="wordnet_lookup",
        runtime_reason=(
            f"Found {len(terms)} polysemous term(s) via WordNet."
            if terms
            else "No polysemous terms found in this sentence."
        ),
    )


def get_polysemy_status() -> dict[str, object]:
    """Plain-English runtime status (mirrors slate_diversity helper)."""
    wordnet = _try_import_wordnet()
    if wordnet is None:
        return {
            "available": False,
            "path": "no_wordnet",
            "reason": (
                "WordNet (NLTK) not installed in this environment. "
                "Polysemy gating is a no-op until NLTK + the WordNet "
                "corpus are added."
            ),
        }
    return {
        "available": True,
        "path": "wordnet_lookup",
        "reason": "WordNet is available; polysemy detection is active.",
    }
