"""Seed AppSetting defaults for the three anti-garbage anchor algos.

Three composable algorithms feeding one additive ``score_final``
contribution per ranker candidate:

- **Algo 1** Aho-Corasick generic-anchor blacklist
  (Aho & Corasick 1975 CACM 18(6) §2)
- **Algo 2** Damerau-Levenshtein + char-trigram Jaccard
  descriptiveness (Damerau 1964 CACM + Broder 1997 SEQUENCES)
- **Algo 3** Shannon character-bigram entropy + Iglewicz-Hoaglin
  modified z-score outlier detection (Shannon 1948 Bell Sys. Tech.
  J. + Iglewicz-Hoaglin 1993 ASTM Quality Control Reference Vol 16)

Idempotent ``update_or_create`` upserts so re-running on an
installation that already has these rows just refreshes the
descriptions. Cold-start byte-stable: contribution stays at 0.0
until at least one algo's input matches a non-neutral pattern AND
``anchor_garbage_signals.ranking_weight`` is non-zero.
"""

from __future__ import annotations

from django.db import migrations


_KEYS = [
    # ── Master dispatcher ────────────────────────────────────────
    (
        "anchor_garbage_signals.enabled",
        "true",
        "PR-Anchor master killswitch. When false, the entire dispatcher "
        "short-circuits regardless of individual algo flags or weights.",
        "ranking",
        "bool",
    ),
    (
        "anchor_garbage_signals.ranking_weight",
        "0.05",
        "Dispatcher ranking weight applied to the [-1, +1] composite "
        "anchor-genericness score. 0.05 matches the Phase 6 "
        "VADER/KenLM/Node2Vec/BPR baseline so the contribution is a "
        "fine-tune signal, not a dominator.",
        "ranking",
        "float",
    ),
    # ── Algo 1 — Aho-Corasick generic blacklist ──────────────────
    (
        "generic_anchor_matcher.enabled",
        "true",
        "Algo 1 — Aho-Corasick blacklist matcher. Source: "
        "Aho & Corasick (1975) CACM 18(6) §2.",
        "ranking",
        "bool",
    ),
    (
        "generic_anchor_matcher.lexicon_path",
        "",
        "Path to the lexicon file. Empty = use the bundled "
        "apps/sources/generic_anchors.txt (~120 curated phrases).",
        "ranking",
        "str",
    ),
    (
        "generic_anchor_matcher.extra_phrases",
        "",
        "Operator-supplied additional generic phrases, newline "
        "separated. Lower-case; '#' lines are comments. Combined "
        "with the lexicon at automaton-build time.",
        "ranking",
        "str",
    ),
    # ── Algo 2 — Descriptiveness ────────────────────────────────
    (
        "anchor_descriptiveness.enabled",
        "true",
        "Algo 2 — Damerau-Levenshtein + char-trigram Jaccard. Source: "
        "Damerau (1964) CACM + Broder (1997) SEQUENCES.",
        "ranking",
        "bool",
    ),
    (
        "anchor_descriptiveness.edit_distance_weight",
        "0.5",
        "Weight of the edit-distance-vs-URL-slug term in the composite "
        "descriptiveness score. Penalises manufactured exact-match "
        "anchors. Range [0, 1]; sum with jaccard_weight typically = 1.0.",
        "ranking",
        "float",
    ),
    (
        "anchor_descriptiveness.jaccard_weight",
        "0.5",
        "Weight of the char-trigram Jaccard term (anchor vs destination "
        "title). Rewards literal lexical overlap robust to morphology.",
        "ranking",
        "float",
    ),
    # ── Algo 3 — Self-information ────────────────────────────────
    (
        "anchor_self_information.enabled",
        "true",
        "Algo 3 — Shannon character-bigram entropy + Iglewicz-Hoaglin "
        "modified z-score. Source: Shannon (1948) Bell Sys. Tech. J. "
        "+ Iglewicz-Hoaglin (1993) ASTM.",
        "ranking",
        "bool",
    ),
    (
        "anchor_self_information.modified_z_threshold",
        "3.5",
        "Iglewicz-Hoaglin (1993) §3 recommended outlier cutoff for the "
        "modified z-score. |M_i| above this triggers the anomaly "
        "penalty. Lower = stricter (more anchors flagged).",
        "ranking",
        "float",
    ),
    (
        "anchor_self_information.corpus_entropy_median",
        "4.0",
        "Median character-bigram entropy across the anchor corpus. "
        "Sensible-English baseline (~4 bits) until the W1 "
        "anchor_self_information_corpus_stats_refresh job writes a "
        "real value.",
        "ranking",
        "float",
    ),
    (
        "anchor_self_information.corpus_entropy_mad",
        "0.5",
        "MAD (median absolute deviation) of corpus bigram entropy. "
        "Sensible-English baseline (~0.5) until the W1 job refits.",
        "ranking",
        "float",
    ),
]


def seed_anti_garbage_anchor_defaults(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for key, value, description, category, value_type in _KEYS:
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": description,
                "category": category,
                "value_type": value_type,
            },
        )


def reverse_seed(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.filter(key__in=[k for k, *_ in _KEYS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0046_seed_phase6_ranker_weights"),
        ("core", "0013_seed_embedding_provider_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_anti_garbage_anchor_defaults, reverse_seed),
    ]
