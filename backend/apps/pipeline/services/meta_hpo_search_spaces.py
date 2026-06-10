"""TPE search spaces — single source of truth for what Option B tunes.

Phase 7 (Slice 15) made this space **registry-driven**: the live
``SEARCH_SPACE`` is assembled by :func:`build_search_space`, which
combines a small set of legacy hand-written entries with entries
**derived at runtime from the canonical tunable registry**
(``apps.suggestions.tunable_registry``). A tunable registered in the
registry therefore appears in the Optuna search space automatically —
**no edit to this module or any tuner code is required.**

**Policy rules baked in here:**

1. **Correctness params are excluded.** Bloom FPR, HLL precision,
   Kernel SHAP `nsamples`, Conformal ``alpha``, Google quota caps, and
   any RFC-mandated behaviour stays fixed forever. They never appear in
   the registry, so they never reach the search space.
2. **Paper-backed bounds.** Every distribution's min/max comes from the
   cited paper / empirical reasonable range — the registry stores the
   ``citation`` next to each bound.
3. **No DB writes from this module.** It only *describes* the space.
   Writing happens in :mod:`meta_hpo` after safety gates pass.
4. **§F boundary — offline-only (``ranking_train``).** Deriving and
   sampling the search space TRAINS / COMPARES candidate profiles
   offline. Nothing here activates, promotes, or rolls back a profile;
   activation stays gated by Rust governance + GUI approval.

Adding a new tunable: add ONE entry to ``META_PARAMS`` /
``BLEND_WEIGHTS`` / ``CONDITIONAL_BLEND_WEIGHTS`` in
``apps.suggestions.tunable_registry``. The deriver picks it up on the
next study run — that is the Phase 7 "no tuner-code change per new
tunable" payoff. Legacy hand-written entries below cover the handful of
TPE-tuned keys that are not (yet) in the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import optuna
from optuna.trial import Trial


@dataclass(frozen=True)
class SearchSpaceEntry:
    """One TPE-tuned hyperparameter.

    - ``app_setting_key``: the ``AppSetting.key`` this tunes (dotted
      string, e.g. ``"reciprocal_rank_fusion.k"``).
    - ``pick_number``: the plan-spec pick number (for dashboard grouping
      + debugging).
    - ``suggest``: a callable that draws a value from an
      :class:`optuna.trial.Trial`. Lets us use any Optuna distribution
      (``suggest_int``, ``suggest_float``, ``suggest_categorical``)
      without hand-rolling switch statements elsewhere.
    - ``clip``: a callable that clamps an arbitrary float back into
      the spec's bounds. Used by the safety rails to force a proposed
      value into the approved range before it's written.
    - ``to_appsetting``: serialiser — the value AppSetting will
      store (string; Django converts on read).
    """

    app_setting_key: str
    pick_number: int
    suggest: Callable[[Trial], Any]
    clip: Callable[[float], float]
    to_appsetting: Callable[[Any], str]


# ── helpers for common shapes ──────────────────────────────────────


def _suggest_float(name: str, lo: float, hi: float, *, log: bool = False):
    return lambda trial: trial.suggest_float(name, lo, hi, log=log)


def _suggest_int(name: str, lo: int, hi: int):
    return lambda trial: trial.suggest_int(name, lo, hi)


def _suggest_categorical(name: str, choices: list):
    return lambda trial: trial.suggest_categorical(name, choices)


def _clip(lo, hi):
    return lambda v: max(lo, min(hi, v))


def _clip_categorical(choices: list):
    def _inner(v):
        # categorical values pass through unchanged when in-set; else
        # snap to the first choice. Only matters under adversarial input;
        # Optuna itself only emits in-set values.
        return v if v in choices else choices[0]

    return _inner


# ── FR-099..FR-105 burn-in gate ────────────────────────────────────
#
# BLC §7.3 rule: no hyperparameter enters the TPE search space until it
# has 30 days of outcome data. FR-099..FR-105 signals all ship with
# researched defaults and stay fixed during the burn-in period.
# `is_fr099_fr105_tpe_eligible()` returns True only when
# SuggestionPresentation has ≥ 30 days of history, at which point the
# guarded entries below join the live search space.


def is_fr099_fr105_tpe_eligible() -> bool:
    """Return True iff we have ≥ 30 days of suggestion outcome data.

    Source: BLC §6.4 + §7.3. Before the 30-day burn-in completes,
    FR-099..FR-105 weights stay at the researched starting values from
    each spec's §Researched Starting Point.
    """
    try:
        from datetime import timedelta

        from django.utils import timezone

        from apps.suggestions.models import SuggestionPresentation

        cutoff = timezone.now() - timedelta(days=30)
        if not SuggestionPresentation.objects.filter(
            first_seen_at__lte=cutoff
        ).exists():
            return False
        # Also require ≥ 100 rows per BLC §6.4 minimum-data floor.
        return SuggestionPresentation.objects.count() >= 100
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
        # Any schema / availability issue → stay ineligible (safe).
        return False


# ── Legacy hand-written TPE-tuned keys ─────────────────────────────
#
# These are the TPE-tuned picks that are not (yet) mirrored in the
# canonical tunable registry — keys like ``trustrank.damping`` and
# ``query_expansion_bow.alpha`` that the registry does not own. They are
# combined with the registry-derived entries by :func:`build_search_space`.
# When a key here is later added to the registry, the registry entry
# wins (see ``_REGISTRY_PRECEDENCE`` in :func:`build_search_space`) and
# the legacy entry can be deleted.
#
# Order mirrors the plan manifest. Each block cites its pick spec §6
# TPE row so reviewers can audit against the source of truth.


_LEGACY_SEARCH_SPACE: list[SearchSpaceEntry] = [
    # pick #27 — Query Expansion BoW (Rocchio α / β)
    SearchSpaceEntry(
        app_setting_key="query_expansion_bow.alpha",
        pick_number=27,
        suggest=_suggest_float("query_expansion_bow.alpha", 0.3, 2.0),
        clip=_clip(0.3, 2.0),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    SearchSpaceEntry(
        app_setting_key="query_expansion_bow.beta",
        pick_number=27,
        suggest=_suggest_float("query_expansion_bow.beta", 0.1, 1.5),
        clip=_clip(0.1, 1.5),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #28 — QL-Dirichlet μ
    SearchSpaceEntry(
        app_setting_key="query_likelihood.dirichlet_mu",
        pick_number=28,
        suggest=_suggest_float(
            "query_likelihood.dirichlet_mu", 100.0, 10_000.0, log=True
        ),
        clip=_clip(100.0, 10_000.0),
        to_appsetting=lambda v: f"{float(v):.1f}",
    ),
    # pick #30 — TrustRank damping
    SearchSpaceEntry(
        app_setting_key="trustrank.damping",
        pick_number=30,
        suggest=_suggest_float("trustrank.damping", 0.6, 0.95),
        clip=_clip(0.6, 0.95),
        to_appsetting=lambda v: f"{float(v):.3f}",
    ),
    # pick #31 — RRF k
    SearchSpaceEntry(
        app_setting_key="reciprocal_rank_fusion.k",
        pick_number=31,
        suggest=_suggest_int("reciprocal_rank_fusion.k", 10, 300),
        clip=_clip(10, 300),
        to_appsetting=lambda v: str(int(v)),
    ),
    # pick #33 — Position-bias IPS η
    SearchSpaceEntry(
        app_setting_key="position_bias_ips.eta",
        pick_number=33,
        suggest=_suggest_float("position_bias_ips.eta", 0.2, 3.0),
        clip=_clip(0.2, 3.0),
        to_appsetting=lambda v: f"{float(v):.3f}",
    ),
    # pick #34 — Cascade click prior α
    SearchSpaceEntry(
        app_setting_key="cascade_click.prior_alpha",
        pick_number=34,
        suggest=_suggest_float("cascade_click.prior_alpha", 0.1, 5.0),
        clip=_clip(0.1, 5.0),
        to_appsetting=lambda v: f"{float(v):.3f}",
    ),
    # pick #35 — Elo K-factor
    SearchSpaceEntry(
        app_setting_key="elo_rating.k_factor",
        pick_number=35,
        suggest=_suggest_float("elo_rating.k_factor", 8.0, 64.0),
        clip=_clip(8.0, 64.0),
        to_appsetting=lambda v: f"{float(v):.1f}",
    ),
    # pick #36 — Personalized PageRank damping
    SearchSpaceEntry(
        app_setting_key="personalized_pagerank.damping",
        pick_number=36,
        suggest=_suggest_float("personalized_pagerank.damping", 0.6, 0.95),
        clip=_clip(0.6, 0.95),
        to_appsetting=lambda v: f"{float(v):.3f}",
    ),
    # pick #40 — EMA α
    SearchSpaceEntry(
        app_setting_key="ema_aggregator.alpha",
        pick_number=40,
        suggest=_suggest_float("ema_aggregator.alpha", 0.01, 0.5),
        clip=_clip(0.01, 0.5),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #49 — Uncertainty sampling strategy (categorical)
    SearchSpaceEntry(
        app_setting_key="uncertainty_sampling.strategy",
        pick_number=49,
        suggest=_suggest_categorical(
            "uncertainty_sampling.strategy",
            ["least_confidence", "margin", "entropy"],
        ),
        clip=_clip_categorical(["least_confidence", "margin", "entropy"]),
        to_appsetting=lambda v: str(v),
    ),
    # pick #52 — Adaptive Conformal Inference γ
    SearchSpaceEntry(
        app_setting_key="adaptive_conformal_inference.learning_rate_gamma",
        pick_number=52,
        suggest=_suggest_float(
            "adaptive_conformal_inference.learning_rate_gamma",
            1e-4,
            0.1,
            log=True,
        ),
        clip=_clip(1e-4, 0.1),
        to_appsetting=lambda v: f"{float(v):.6f}",
    ),
]


# ── FR-099..FR-105 TPE entries (added after 30-day burn-in completes) ──
#
# These live in a separate list so the eligibility gate can splice them
# into SEARCH_SPACE only after SuggestionPresentation has ≥ 30 days of
# data. Bounds come from each spec's §Researched Starting Point +
# §Hardware Budget magnitude band. pick_number is the FR number for
# dashboard grouping.

_FR099_FR105_ENTRIES: list[SearchSpaceEntry] = [
    # FR-099 DARB ranking_weight — Page et al. 1999 §3.2 eq. 1 magnitude band
    SearchSpaceEntry(
        app_setting_key="darb.ranking_weight",
        pick_number=99,
        suggest=_suggest_float("darb.ranking_weight", 0.01, 0.10),
        clip=_clip(0.01, 0.10),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # FR-100 KMIG ranking_weight — Katz 1953 §3 attenuated-status magnitude
    SearchSpaceEntry(
        app_setting_key="kmig.ranking_weight",
        pick_number=100,
        suggest=_suggest_float("kmig.ranking_weight", 0.01, 0.12),
        clip=_clip(0.01, 0.12),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # FR-101 TAPB ranking_weight — Tarjan 1972 §3 articulation-point rarity band
    SearchSpaceEntry(
        app_setting_key="tapb.ranking_weight",
        pick_number=101,
        suggest=_suggest_float("tapb.ranking_weight", 0.01, 0.08),
        clip=_clip(0.01, 0.08),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # FR-102 KCIB ranking_weight — Seidman 1983 §4 k-core distribution magnitude
    SearchSpaceEntry(
        app_setting_key="kcib.ranking_weight",
        pick_number=102,
        suggest=_suggest_float("kcib.ranking_weight", 0.01, 0.08),
        clip=_clip(0.01, 0.08),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # FR-103 BERP ranking_weight — Hopcroft-Tarjan 1973 §2 bridge-edge rarity band
    SearchSpaceEntry(
        app_setting_key="berp.ranking_weight",
        pick_number=103,
        suggest=_suggest_float("berp.ranking_weight", 0.01, 0.10),
        clip=_clip(0.01, 0.10),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # FR-104 HGTE ranking_weight — Shannon 1948 §6 entropy magnitude band
    SearchSpaceEntry(
        app_setting_key="hgte.ranking_weight",
        pick_number=104,
        suggest=_suggest_float("hgte.ranking_weight", 0.01, 0.10),
        clip=_clip(0.01, 0.10),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # FR-105 RSQVA ranking_weight — Salton & Buckley 1988 §5 cosine-sim magnitude
    SearchSpaceEntry(
        app_setting_key="rsqva.ranking_weight",
        pick_number=105,
        suggest=_suggest_float("rsqva.ranking_weight", 0.01, 0.12),
        clip=_clip(0.01, 0.12),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
]

_GROUP_G_HARMONIOUS_12_ENTRIES: list[SearchSpaceEntry] = [
    # pick #56 — Phrase Matching weight
    SearchSpaceEntry(
        app_setting_key="phrase_matching.ranking_weight",
        pick_number=56,
        suggest=_suggest_float("phrase_matching.ranking_weight", 0.01, 0.20),
        clip=_clip(0.01, 0.20),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #55 — Noun Chunk Boost weight
    SearchSpaceEntry(
        app_setting_key="phrase_matching.noun_chunk_boost_weight",
        pick_number=55,
        suggest=_suggest_float("phrase_matching.noun_chunk_boost_weight", 0.0, 0.15),
        clip=_clip(0.0, 0.15),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #62 — Fuzzy Match weight
    SearchSpaceEntry(
        app_setting_key="phrase_matching.fuzzy_match_weight",
        pick_number=62,
        suggest=_suggest_float("phrase_matching.fuzzy_match_weight", 0.0, 0.15),
        clip=_clip(0.0, 0.15),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #64 — JSD Boost weight
    SearchSpaceEntry(
        app_setting_key="phrase_matching.jsd_boost_weight",
        pick_number=64,
        suggest=_suggest_float("phrase_matching.jsd_boost_weight", 0.0, 0.15),
        clip=_clip(0.0, 0.15),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #57 — Lexical Richness weight
    SearchSpaceEntry(
        app_setting_key="phrase_matching.lexical_richness_weight",
        pick_number=57,
        suggest=_suggest_float("phrase_matching.lexical_richness_weight", 0.0, 0.10),
        clip=_clip(0.0, 0.10),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #61 — Phonetic Boost weight
    SearchSpaceEntry(
        app_setting_key="phrase_matching.phonetic_boost_weight",
        pick_number=61,
        suggest=_suggest_float("phrase_matching.phonetic_boost_weight", 0.0, 0.10),
        clip=_clip(0.0, 0.10),
        to_appsetting=lambda v: f"{float(v):.4f}",
    ),
    # pick #54 — Lemma enabled (categorical)
    SearchSpaceEntry(
        app_setting_key="lemma.enabled",
        pick_number=54,
        suggest=_suggest_categorical("lemma.enabled", ["true", "false"]),
        clip=_clip_categorical(["true", "false"]),
        to_appsetting=lambda v: str(v),
    ),
]


# Splice FR-099..FR-105 into the legacy list iff the burn-in gate passes.
# Evaluated at module-import time (stable for the process lifetime).
if is_fr099_fr105_tpe_eligible():
    _LEGACY_SEARCH_SPACE.extend(_FR099_FR105_ENTRIES)
    _LEGACY_SEARCH_SPACE.extend(_GROUP_G_HARMONIOUS_12_ENTRIES)


# ── Registry-driven derivation (Phase 7 heart) ─────────────────────
#
# The deriver turns each canonical-registry ``TunableEntry`` into a
# ``SearchSpaceEntry`` whose ``suggest`` / ``clip`` / ``to_appsetting``
# callables are inferred from the registry's ``lower`` / ``upper`` /
# ``default`` fields. A registry entry therefore becomes an Optuna
# distribution with NO per-entry callable hand-coded here — the Phase 7
# "no tuner-code change per new tunable" guarantee.


def _looks_like_int(default: str) -> bool:
    """True when the registry default is an integer literal (no decimal).

    The registry stores defaults as strings (``"60"`` vs ``"1.2"``). An
    integer-looking default + whole-number bounds means the knob should
    use an integer Optuna distribution and an integer serialiser so the
    written AppSetting value round-trips without a spurious ``.0``.
    """
    text = (default or "").strip()
    if not text:
        return False
    try:
        as_float = float(text)
    except (TypeError, ValueError):
        return False
    return "." not in text and "e" not in text.lower() and as_float == int(as_float)


def _int_serialiser(value: Any) -> str:
    return str(int(round(float(value))))


def _float_serialiser(value: Any) -> str:
    return f"{float(value):.4f}"


def derive_entry(key: str, lower: float, upper: float, default: str) -> SearchSpaceEntry:
    """Build one :class:`SearchSpaceEntry` from registry bound fields.

    Distribution + serialiser are chosen from ``default``: an integer
    literal yields ``suggest_int`` + an int serialiser, anything else a
    ``suggest_float`` + a 4-dp serialiser. ``clip`` clamps into
    ``[lower, upper]`` exactly as the legacy entries do.
    """
    if _looks_like_int(default):
        lo_i, hi_i = int(round(lower)), int(round(upper))
        return SearchSpaceEntry(
            app_setting_key=key,
            pick_number=0,  # 0 = registry-derived (no plan-spec pick number)
            suggest=_suggest_int(key, lo_i, hi_i),
            clip=_clip(lo_i, hi_i),
            to_appsetting=_int_serialiser,
        )
    return SearchSpaceEntry(
        app_setting_key=key,
        pick_number=0,
        suggest=_suggest_float(key, float(lower), float(upper)),
        clip=_clip(float(lower), float(upper)),
        to_appsetting=_float_serialiser,
    )


def derive_registry_search_space() -> list[SearchSpaceEntry]:
    """Derive search-space entries from the canonical tunable registry.

    Reads ``META_PARAMS``, ``BLEND_WEIGHTS``, and the candidate weight of
    each ``CONDITIONAL_BLEND_WEIGHTS`` entry. Excluded meta keys are
    skipped — they are deliberately not auto-tuned. The registry is
    imported lazily and read fresh on every call so a test (or a new
    tunable registered at runtime) is reflected without re-importing this
    module.
    """
    from apps.suggestions.tunable_registry import (
        BLEND_WEIGHTS,
        CONDITIONAL_BLEND_WEIGHTS,
        META_PARAMS,
        META_PARAMS_EXCLUDED,
    )

    derived: list[SearchSpaceEntry] = []
    seen: set[str] = set()

    def _add(key: str, entry) -> None:
        if key in META_PARAMS_EXCLUDED or key in seen:
            return
        seen.add(key)
        derived.append(
            derive_entry(key, entry.lower, entry.upper, entry.default)
        )

    for key, entry in META_PARAMS.items():
        _add(key, entry)
    for key, entry in BLEND_WEIGHTS.items():
        _add(key, entry)
    for weight_key, (_gate_key, entry) in CONDITIONAL_BLEND_WEIGHTS.items():
        _add(weight_key, entry)

    return derived


def build_search_space() -> list[SearchSpaceEntry]:
    """Assemble the live search space: registry-derived + legacy entries.

    The registry is the single source of truth, so registry-derived
    entries take precedence: a legacy hand-written entry whose key the
    registry now owns is dropped in favour of the registry-derived one.
    Legacy entries that the registry does not own (e.g.
    ``trustrank.damping``) are appended after.
    """
    derived = derive_registry_search_space()
    derived_keys = {entry.app_setting_key for entry in derived}
    combined = list(derived)
    for entry in _LEGACY_SEARCH_SPACE:
        if entry.app_setting_key not in derived_keys:
            combined.append(entry)
    return combined


def rebuild_search_space() -> list[SearchSpaceEntry]:
    """Rebuild the module-level ``SEARCH_SPACE`` from the current registry.

    ``meta_hpo`` iterates the module-level ``SEARCH_SPACE`` list object,
    so we mutate it in place (rather than rebind) to keep that reference
    live. Returns the rebuilt list for convenience.
    """
    SEARCH_SPACE[:] = build_search_space()
    return SEARCH_SPACE


#: The live search space the study iterates. Registry-driven: rebuilt
#: from the registry at import time and re-buildable via
#: :func:`rebuild_search_space` (e.g. before each weekly study run, so a
#: tunable registered since process start is picked up).
SEARCH_SPACE: list[SearchSpaceEntry] = build_search_space()


# ── Study-level constants ─────────────────────────────────────────


#: SQLite file for the Optuna study. Survives laptop restarts.
DEFAULT_STORAGE_URL: str = "sqlite:///var/optuna/meta_hpo.db"

#: Fixed seed so the study's "best trial" number is reproducible
#: when an operator compares runs.
DEFAULT_SEED: int = 42

#: Number of Optuna trials per weekly run. 200 is the plan-spec
#: default; fits inside the 60–120 min scheduler estimate.
DEFAULT_N_TRIALS: int = 200


def sample_params(trial: Trial) -> dict[str, Any]:
    """Draw one trial's full parameter dict from the search space."""
    return {entry.app_setting_key: entry.suggest(trial) for entry in SEARCH_SPACE}


def clip_params(params: dict[str, Any]) -> dict[str, Any]:
    """Clamp each param into its spec-bound range.

    Used by :mod:`meta_hpo_safety` before any write-back to AppSetting.
    """
    clipped: dict[str, Any] = {}
    for entry in SEARCH_SPACE:
        if entry.app_setting_key in params:
            clipped[entry.app_setting_key] = entry.clip(params[entry.app_setting_key])
    return clipped


def keys() -> list[str]:
    """Return the ordered list of AppSetting keys this study controls."""
    return [entry.app_setting_key for entry in SEARCH_SPACE]


def make_sampler() -> optuna.samplers.TPESampler:
    """Return the sampler with the project's fixed seed for reproducibility."""
    return optuna.samplers.TPESampler(seed=DEFAULT_SEED)


def make_pruner() -> optuna.pruners.MedianPruner:
    """Return the median pruner — stops clearly-bad trials early."""
    return optuna.pruners.MedianPruner(n_warmup_steps=5)
