"""Anti-generic / pro-descriptive anchor-text signals (3 algos).

Three independent, non-overlapping algorithms that together flag
"click here" / SEO-template / off-topic anchors and reward
descriptive ones. All three feed a single additive
``score_anchor_genericness`` ∈ [-1, +1] contribution to the ranker.

References
----------
Algorithm 1 — Aho-Corasick generic-phrase matcher
    Aho, A. V., & Corasick, M. J. (1975). "Efficient String Matching:
    An Aid to Bibliographic Search." *Communications of the ACM*,
    18(6), 333-340.

Algorithm 2 — Damerau-Levenshtein + Jaccard descriptiveness
    Damerau, F. J. (1964). "A technique for computer detection and
    correction of spelling errors." *CACM*, 7(3), 171-176.
    Broder, A. Z. (1997). "On the Resemblance and Containment of
    Documents." *Compression and Complexity of Sequences*.

Algorithm 3 — Shannon entropy + Iglewicz-Hoaglin modified z-score
    Shannon, C. E. (1948). "A Mathematical Theory of Communication."
    *Bell System Technical Journal*, 27(3+4).
    Iglewicz, B., & Hoaglin, D. (1993). "How to Detect and Handle
    Outliers." ASQC / ASTM Quality Control Reference Vol 16.

Why these three and not others
-------------------------------
Existing anchor-related code:
  - ``anchor_diversity``        — Salton 1988 IDF-variance over
                                   repeated anchors per host
  - ``anchor_extractor``        — anchor-candidate extraction
  - ``learned_anchor``          — operator-approval corroboration
  - ``keyword_stuffing``        — Lavrenko-Croft keyword density
                                   in DESTINATION TITLES
  - ``link_farm``               — Gyöngyi-Garcia-Molina graph cycles
  - ``phrase_matching``         — Robertson 1994 BM25 anchor↔dest

None of those check anchor text against a curated generic-phrase
blacklist, none compute character-level Jaccard between anchor and
destination, and none look at anchor self-information / entropy.
The three algos here sit in a clean, additive surface.

Cold-start safety
-----------------
Every helper returns 0.0 (or its neutral default) when:
- The C++ kernel isn't built (Python fallback fires instead).
- The lexicon file is empty / missing.
- The AppSetting toggle is off.
- The input is empty.

Empty / missing inputs are not "negative evidence" — they are
"absence of evidence", and the helpers reflect that.

Wiring
------
``apps.pipeline.services.ranker.score_destination_matches`` reads
the dispatcher built by :func:`build_anchor_garbage_signals` and
adds ``ranking_weight × evaluate_all(...).score_anchor_genericness``
to ``score_final`` per candidate. Same Pattern-A sidecar used by
``graph_signal_ranker`` and ``phase6_ranker_contribution``.
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Mapping

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Constants — paper-backed defaults
# ─────────────────────────────────────────────────────────────────────


#: Iglewicz-Hoaglin 1993 §3 recommended outlier threshold for the
#: modified z-score using MAD. Values with |M_i| above this are
#: flagged as outliers.
DEFAULT_MODIFIED_Z_THRESHOLD: float = 3.5

#: Iglewicz-Hoaglin 1993 §2 conversion factor — 0.6745 is the inverse
#: of the standard normal's 75th percentile, making the modified
#: z-score asymptotically equivalent to a standard z-score for normal
#: data. NOT operator-tunable; this is a math constant.
_IGLEWICZ_HOAGLIN_CONSTANT: float = 0.6745

#: Sensible English-text bigram-entropy baseline used until the
#: weekly ``anchor_self_information_corpus_stats_refresh`` W1 job
#: writes real corpus stats. Median ~4 bits, MAD ~0.5 — derived
#: from typical English news-text bigram counts (Shannon 1951
#: §4 cited as the lower bound; modern English ≈ 4.5 bits/char).
DEFAULT_CORPUS_ENTROPY_MEDIAN: float = 4.0
DEFAULT_CORPUS_ENTROPY_MAD: float = 0.5

#: Character-trigram length used for Jaccard similarity. 3 is the
#: classic Damerau / Broder choice — robust to plurals, suffixes,
#: minor case differences.
_CHAR_NGRAM: int = 3

#: AppSetting keys — lined up with the seed migration so the
#: dispatcher and the operator-tunable knobs share the same names.
KEY_DISPATCHER_ENABLED = "anchor_garbage_signals.enabled"
KEY_DISPATCHER_WEIGHT = "anchor_garbage_signals.ranking_weight"
KEY_GENERIC_ENABLED = "generic_anchor_matcher.enabled"
KEY_GENERIC_LEXICON_PATH = "generic_anchor_matcher.lexicon_path"
KEY_GENERIC_EXTRA_PHRASES = "generic_anchor_matcher.extra_phrases"
KEY_DESCR_ENABLED = "anchor_descriptiveness.enabled"
KEY_DESCR_EDIT_WEIGHT = "anchor_descriptiveness.edit_distance_weight"
KEY_DESCR_JACCARD_WEIGHT = "anchor_descriptiveness.jaccard_weight"
KEY_SELF_INFO_ENABLED = "anchor_self_information.enabled"
KEY_SELF_INFO_THRESHOLD = "anchor_self_information.modified_z_threshold"
KEY_CORPUS_ENTROPY_MEDIAN = "anchor_self_information.corpus_entropy_median"
KEY_CORPUS_ENTROPY_MAD = "anchor_self_information.corpus_entropy_mad"

#: Path the lexicon ships at by default. Operators can point at a
#: different file via ``KEY_GENERIC_LEXICON_PATH``.
_DEFAULT_LEXICON_PATH = os.path.join(
    os.path.dirname(
        os.path.dirname(__file__)
    ),  # apps/pipeline/services → apps/pipeline → apps
    "..",
    "sources",
    "generic_anchors.txt",
)


# ─────────────────────────────────────────────────────────────────────
# C++ kernel binding — falls back to pure-Python when not built
# ─────────────────────────────────────────────────────────────────────


try:  # pragma: no cover — depends on whether the .so was compiled
    from extensions import generic_anchor_matcher as _cpp_matcher  # type: ignore[import]

    _HAS_CPP_MATCHER = True
except ImportError:
    _cpp_matcher = None  # type: ignore[assignment]
    _HAS_CPP_MATCHER = False

try:  # pragma: no cover
    from extensions import anchor_descriptiveness as _cpp_descr  # type: ignore[import]

    _HAS_CPP_DESCR = True
except ImportError:
    _cpp_descr = None  # type: ignore[assignment]
    _HAS_CPP_DESCR = False

try:  # pragma: no cover
    from extensions import anchor_self_information as _cpp_self_info  # type: ignore[import]

    _HAS_CPP_SELF_INFO = True
except ImportError:
    _cpp_self_info = None  # type: ignore[assignment]
    _HAS_CPP_SELF_INFO = False


# ─────────────────────────────────────────────────────────────────────
# Algorithm 1 — generic-phrase Aho-Corasick matcher
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GenericMatchResult:
    """Output of the generic-anchor matcher."""

    matched: bool
    matched_phrases: tuple[str, ...]
    #: ``len(matched_phrases) / max(1, words_in_anchor)``. Higher =
    #: more of the anchor is generic. Bounded to [0, 1].
    genericness: float


def _load_lexicon(*, lexicon_path: str | None = None) -> tuple[str, ...]:
    """Read the curated lexicon + any operator-supplied extras.

    Cold-start safe: missing file → empty tuple → matcher reports
    ``matched=False`` for everything.
    """
    phrases: list[str] = []
    path = lexicon_path or _DEFAULT_LEXICON_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip().lower()
                if not line or line.startswith("#"):
                    continue
                phrases.append(line)
    except OSError:
        logger.debug("anchor_garbage: lexicon file %s not readable", path)
    # Operator-supplied extras via AppSetting (newline-separated).
    try:
        from apps.core.models import AppSetting

        extra_row = AppSetting.objects.filter(key=KEY_GENERIC_EXTRA_PHRASES).first()
        if extra_row and extra_row.value:
            for raw in extra_row.value.splitlines():
                line = raw.strip().lower()
                if line and not line.startswith("#"):
                    phrases.append(line)
    except Exception:
        # AppSetting unreachable (test env / migrations not run) →
        # operator-extras path is just skipped, lexicon-from-disk
        # still works.
        pass
    return tuple(phrases)


@lru_cache(maxsize=4)
def _compiled_lexicon(lexicon_path: str | None) -> tuple[tuple[str, ...], object]:
    """Return ``(phrases, compiled_matcher_or_None)`` for *lexicon_path*.

    When the C++ kernel is built, ``compiled_matcher_or_None`` is the
    Aho-Corasick automaton. When it isn't, returns ``None`` and the
    Python fallback iterates the phrase list (slower but correct).

    Cached on path so multiple calls don't re-read the file.
    """
    phrases = _load_lexicon(lexicon_path=lexicon_path)
    if not phrases:
        return phrases, None
    if _HAS_CPP_MATCHER and _cpp_matcher is not None:
        try:
            automaton = _cpp_matcher.build_automaton(list(phrases))  # type: ignore[union-attr]
            return phrases, automaton
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("anchor_garbage: C++ build failed: %s", exc)
    return phrases, None


def generic_score(
    anchor: str, *, lexicon_path: str | None = None
) -> GenericMatchResult:
    """Return matched generic phrases + a [0, 1] genericness ratio.

    Cold-start safe: empty anchor / disabled toggle / missing
    lexicon → ``GenericMatchResult(False, (), 0.0)``.
    """
    if not anchor or not anchor.strip():
        return GenericMatchResult(matched=False, matched_phrases=(), genericness=0.0)
    try:
        from apps.core.runtime_flags import is_enabled

        if not is_enabled(KEY_GENERIC_ENABLED, default=True):
            return GenericMatchResult(False, (), 0.0)
    except Exception:
        pass
    needle = anchor.lower().strip()
    phrases, automaton = _compiled_lexicon(lexicon_path)
    if not phrases:
        return GenericMatchResult(False, (), 0.0)

    if automaton is not None:  # pragma: no cover — needs C++ build
        try:
            matches = _cpp_matcher.find_all(automaton, needle)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("anchor_garbage: C++ find_all failed: %s", exc)
            matches = _python_find_all(needle, phrases)
    else:
        matches = _python_find_all(needle, phrases)

    if not matches:
        return GenericMatchResult(False, (), 0.0)

    word_count = max(1, len(needle.split()))
    # Genericness = sum of matched-phrase word-counts / anchor word
    # count, clamped to [0, 1]. A 3-word anchor that contains a
    # 3-word generic phrase is 100% generic; a 5-word anchor
    # containing a 2-word match is 40% generic.
    matched_words = sum(len(p.split()) for p in matches)
    genericness = min(1.0, matched_words / word_count)
    return GenericMatchResult(
        matched=True,
        matched_phrases=tuple(matches),
        genericness=float(genericness),
    )


def _python_find_all(needle: str, phrases: tuple[str, ...]) -> list[str]:
    """Pure-Python fallback for the Aho-Corasick matcher.

    Slower than the C++ kernel (O(n × m) vs O(n + m + k)), but
    produces identical match lists. Used in tests + cold-start
    installs where the C++ kernel hasn't been built yet.
    """
    out: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        if phrase in needle and phrase not in seen:
            out.append(phrase)
            seen.add(phrase)
    return out


# ─────────────────────────────────────────────────────────────────────
# Algorithm 2 — Damerau-Levenshtein + char-trigram Jaccard
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DescriptivenessResult:
    """Output of the descriptiveness scorer."""

    edit_distance_ratio: float  # [0, 1]; 0 = identical, 1 = no overlap
    char_trigram_jaccard: float  # [0, 1]; high = lexically descriptive
    score: float  # [-1, +1]; positive = descriptive


def descriptiveness_score(
    anchor: str,
    destination_title: str,
    destination_slug: str = "",
    *,
    edit_distance_weight: float = 0.5,
    jaccard_weight: float = 0.5,
) -> DescriptivenessResult:
    """Score how well *anchor* describes *destination_title*.

    - **Edit-distance to slug**: if the anchor is byte-identical
      to the destination URL slug (or one Damerau-Levenshtein edit
      away), it's a manufactured exact-match SEO anchor — negative
      contribution.
    - **Character-trigram Jaccard with title**: high overlap = anchor
      shares meaningful sub-word units with the title. Robust to
      plurals, suffixes, case differences.
    - **Composite score**: ``jaccard_weight × char_jaccard −
      edit_distance_weight × (1 − edit_distance_ratio)``.

    Cold-start safe: empty inputs return a neutral
    :data:`DescriptivenessResult(0.5, 0.0, 0.0)`.
    """
    if not anchor or not anchor.strip():
        return DescriptivenessResult(
            edit_distance_ratio=1.0, char_trigram_jaccard=0.0, score=0.0
        )
    try:
        from apps.core.runtime_flags import is_enabled

        if not is_enabled(KEY_DESCR_ENABLED, default=True):
            return DescriptivenessResult(1.0, 0.0, 0.0)
    except Exception:
        pass

    a = anchor.lower().strip()
    title = (destination_title or "").lower().strip()
    slug = (destination_slug or "").lower().strip()

    # Edit-distance ratio against the slug (manufactured-match check).
    # Only fires when slug is non-empty.
    if slug:
        dl = _damerau_levenshtein(a, slug)
        max_len = max(len(a), len(slug), 1)
        edit_distance_ratio = min(1.0, dl / max_len)
    else:
        edit_distance_ratio = 1.0  # no slug ⇒ no manufactured-match risk

    # Character-trigram Jaccard against the title (descriptiveness).
    if title:
        char_jaccard = _char_trigram_jaccard(a, title)
    else:
        char_jaccard = 0.0

    # Composite. Manufactured = (1 - edit_distance_ratio) is high
    # when anchor ≈ slug. Subtract its weight; add the Jaccard
    # weight. Clamp to [-1, 1].
    raw = jaccard_weight * char_jaccard - edit_distance_weight * (
        1.0 - edit_distance_ratio
    )
    score = max(-1.0, min(1.0, raw))
    return DescriptivenessResult(
        edit_distance_ratio=float(edit_distance_ratio),
        char_trigram_jaccard=float(char_jaccard),
        score=float(score),
    )


def _damerau_levenshtein(a: str, b: str) -> int:
    """Damerau-Levenshtein distance with O(min(n,m)) memory.

    Falls through to the C++ kernel when available; otherwise the
    pure-Python rolling-row DP is correct for all valid inputs.
    """
    if _HAS_CPP_DESCR and _cpp_descr is not None:  # pragma: no cover — needs build
        try:
            return int(_cpp_descr.damerau_levenshtein(a, b))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("anchor_garbage: C++ damerau_levenshtein failed: %s", exc)
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    n, m = len(a), len(b)
    prev_prev_row = [0] * (m + 1)
    prev_row = list(range(m + 1))
    curr_row = [0] * (m + 1)
    for i in range(1, n + 1):
        curr_row[0] = i
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr_row[j] = min(
                curr_row[j - 1] + 1,  # insertion
                prev_row[j] + 1,  # deletion
                prev_row[j - 1] + cost,  # substitution
            )
            # Damerau extension — adjacent transposition.
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                curr_row[j] = min(curr_row[j], prev_prev_row[j - 2] + cost)
        prev_prev_row, prev_row, curr_row = prev_row, curr_row, prev_prev_row
    return prev_row[m]


def _char_trigram_jaccard(a: str, b: str) -> float:
    """Jaccard similarity over character 3-grams of *a* and *b*."""
    if _HAS_CPP_DESCR and _cpp_descr is not None:  # pragma: no cover — needs build
        try:
            return float(_cpp_descr.char_trigram_jaccard(a, b))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("anchor_garbage: C++ jaccard failed: %s", exc)
    grams_a = _char_ngrams(a, _CHAR_NGRAM)
    grams_b = _char_ngrams(b, _CHAR_NGRAM)
    if not grams_a or not grams_b:
        return 0.0
    inter = len(grams_a & grams_b)
    union = len(grams_a | grams_b)
    return inter / union if union else 0.0


def _char_ngrams(text: str, n: int) -> set[str]:
    """Return the set of character ``n``-grams in *text*. Strips
    consecutive whitespace so two phrases with different spacing
    produce comparable n-gram sets.
    """
    norm = re.sub(r"\s+", " ", text)
    if len(norm) < n:
        return {norm} if norm else set()
    return {norm[i : i + n] for i in range(len(norm) - n + 1)}


# ─────────────────────────────────────────────────────────────────────
# Algorithm 3 — Shannon entropy + Iglewicz-Hoaglin modified z-score
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SelfInformationResult:
    """Output of the self-information / anomaly scorer."""

    entropy: float
    modified_z_score: float
    anomaly_flag: bool
    #: Magnitude of penalty applied (≥ 0). 0 when not flagged.
    anomaly_penalty: float


def self_information_score(
    anchor: str,
    *,
    corpus_median: float | None = None,
    corpus_mad: float | None = None,
    threshold: float | None = None,
) -> SelfInformationResult:
    """Compute the anchor's character-bigram entropy + outlier score.

    Cold-start safe: empty anchor → neutral result. Missing AppSetting
    corpus stats → defaults from :data:`DEFAULT_CORPUS_ENTROPY_MEDIAN`
    + :data:`DEFAULT_CORPUS_ENTROPY_MAD`.
    """
    if not anchor or not anchor.strip():
        return SelfInformationResult(0.0, 0.0, False, 0.0)
    try:
        from apps.core.runtime_flags import is_enabled

        if not is_enabled(KEY_SELF_INFO_ENABLED, default=True):
            return SelfInformationResult(0.0, 0.0, False, 0.0)
    except Exception:
        pass

    entropy = _bigram_entropy(anchor.lower())

    median, mad, thresh = _resolve_corpus_stats(corpus_median, corpus_mad, threshold)

    # Iglewicz-Hoaglin 1993 §2: M_i = 0.6745 × (x_i - median) / MAD.
    # Guard MAD ≥ epsilon so the divide can't blow up.
    if mad < 1e-9:
        modified_z = 0.0
    else:
        modified_z = _IGLEWICZ_HOAGLIN_CONSTANT * (entropy - median) / mad

    anomaly = abs(modified_z) > thresh
    # Penalty magnitude — bounded so a single off-distribution anchor
    # can't wipe ``score_final`` by itself. Linear ramp above the
    # threshold, capped at 1.0 (≥ 7 × MAD from median).
    if anomaly:
        excess = abs(modified_z) - thresh
        penalty = min(1.0, excess / max(thresh, 1e-9))
    else:
        penalty = 0.0
    return SelfInformationResult(
        entropy=float(entropy),
        modified_z_score=float(modified_z),
        anomaly_flag=bool(anomaly),
        anomaly_penalty=float(penalty),
    )


def _bigram_entropy(text: str) -> float:
    """Shannon character-bigram entropy in bits.

    H(X) = -Σ p(x) log₂ p(x) over the bigram distribution. C++
    fast-path falls through to pure Python when not built.
    """
    if (
        _HAS_CPP_SELF_INFO and _cpp_self_info is not None
    ):  # pragma: no cover — needs build
        try:
            return float(_cpp_self_info.bigram_entropy(text))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("anchor_garbage: C++ bigram_entropy failed: %s", exc)
    if len(text) < 2:
        return 0.0
    counts: dict[str, int] = {}
    total = 0
    for i in range(len(text) - 1):
        bg = text[i : i + 2]
        counts[bg] = counts.get(bg, 0) + 1
        total += 1
    if total == 0:
        return 0.0
    h = 0.0
    inv_total = 1.0 / total
    for c in counts.values():
        p = c * inv_total
        h -= p * math.log2(p)
    return h


def _resolve_corpus_stats(
    median: float | None,
    mad: float | None,
    threshold: float | None,
) -> tuple[float, float, float]:
    """Pull corpus stats from AppSetting; fall back to safe defaults."""
    try:
        from apps.core.models import AppSetting

        rows = dict(
            AppSetting.objects.filter(
                key__in=[
                    KEY_CORPUS_ENTROPY_MEDIAN,
                    KEY_CORPUS_ENTROPY_MAD,
                    KEY_SELF_INFO_THRESHOLD,
                ]
            ).values_list("key", "value")
        )
    except Exception:
        rows = {}

    def _f(value: object, fallback: float) -> float:
        try:
            return float(value) if value not in (None, "") else fallback
        except (TypeError, ValueError):
            return fallback

    return (
        median
        if median is not None
        else _f(rows.get(KEY_CORPUS_ENTROPY_MEDIAN), DEFAULT_CORPUS_ENTROPY_MEDIAN),
        mad
        if mad is not None
        else _f(rows.get(KEY_CORPUS_ENTROPY_MAD), DEFAULT_CORPUS_ENTROPY_MAD),
        threshold
        if threshold is not None
        else _f(rows.get(KEY_SELF_INFO_THRESHOLD), DEFAULT_MODIFIED_Z_THRESHOLD),
    )


# ─────────────────────────────────────────────────────────────────────
# Dispatcher — combines the three algos into one additive contribution
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AnchorGarbageEvaluation:
    """Combined result of all three anti-garbage algorithms."""

    generic: GenericMatchResult
    descriptiveness: DescriptivenessResult
    self_information: SelfInformationResult
    #: Composite score in [-1, +1]. Negative = looks generic / spammy
    #: / off-topic; positive = looks descriptive.
    score_anchor_genericness: float


def evaluate_all(
    anchor: str,
    destination_title: str = "",
    destination_slug: str = "",
) -> AnchorGarbageEvaluation:
    """Run all three algorithms; return the composite result.

    The composite math:

        score_anchor_genericness =
            -1 × generic.genericness                # ∈ [0, 1]
            + descriptiveness.score                  # ∈ [-1, +1]
            -1 × self_information.anomaly_penalty   # ∈ [0, 1]

        clamped to [-1, +1]

    Each per-algo result is exposed on the dataclass so the Explain
    panel can surface the breakdown to operators.
    """
    g = generic_score(anchor)
    d = descriptiveness_score(anchor, destination_title, destination_slug)
    s = self_information_score(anchor)
    raw = -g.genericness + d.score - s.anomaly_penalty
    composite = max(-1.0, min(1.0, raw))
    return AnchorGarbageEvaluation(
        generic=g,
        descriptiveness=d,
        self_information=s,
        score_anchor_genericness=float(composite),
    )


@dataclass(frozen=True, slots=True)
class AnchorGarbageDispatcher:
    """Operator-built wrapper that holds the active weight."""

    ranking_weight: float

    def contribution(
        self,
        anchor: str,
        destination_title: str = "",
        destination_slug: str = "",
    ) -> float:
        """Return ``ranking_weight × score_anchor_genericness``.

        Returns ``0.0`` when the dispatcher's ranking_weight is 0.0
        (cold-start byte-stable).
        """
        if self.ranking_weight == 0.0:
            return 0.0
        ev = evaluate_all(anchor, destination_title, destination_slug)
        return float(self.ranking_weight) * ev.score_anchor_genericness


def build_anchor_garbage_signals() -> AnchorGarbageDispatcher | None:
    """Construct the dispatcher from current AppSetting values.

    Returns ``None`` when the master toggle is off or
    ``ranking_weight`` is zero — same shape as
    :func:`apps.pipeline.services.graph_signal_ranker.build_graph_signal_ranker`
    so the ranker call site can short-circuit cleanly.
    """
    try:
        from apps.core.models import AppSetting
        from apps.core.runtime_flags import is_enabled

        if not is_enabled(KEY_DISPATCHER_ENABLED, default=True):
            return None
        row = AppSetting.objects.filter(key=KEY_DISPATCHER_WEIGHT).first()
    except Exception:
        return None
    if row is None or not row.value:
        return None
    try:
        weight = float(row.value)
    except (TypeError, ValueError):
        return None
    if weight == 0.0:
        return None
    return AnchorGarbageDispatcher(ranking_weight=weight)


__all__ = [
    "AnchorGarbageEvaluation",
    "AnchorGarbageDispatcher",
    "DEFAULT_MODIFIED_Z_THRESHOLD",
    "DescriptivenessResult",
    "GenericMatchResult",
    "KEY_CORPUS_ENTROPY_MAD",
    "KEY_CORPUS_ENTROPY_MEDIAN",
    "KEY_DESCR_ENABLED",
    "KEY_DESCR_EDIT_WEIGHT",
    "KEY_DESCR_JACCARD_WEIGHT",
    "KEY_DISPATCHER_ENABLED",
    "KEY_DISPATCHER_WEIGHT",
    "KEY_GENERIC_ENABLED",
    "KEY_GENERIC_EXTRA_PHRASES",
    "KEY_GENERIC_LEXICON_PATH",
    "KEY_SELF_INFO_ENABLED",
    "KEY_SELF_INFO_THRESHOLD",
    "SelfInformationResult",
    "build_anchor_garbage_signals",
    "descriptiveness_score",
    "evaluate_all",
    "generic_score",
    "self_information_score",
]


# Quiet IDE — silence "imported but unused" for fields used in metadata.
_ = Iterable
_ = Mapping
_ = field
