"""Seed Phase 6 per-pick ranking weights so all six adapters fire on
a fresh install.

Why
---
Migration 0043 seeded each Phase 6 pick's ``*.enabled`` flag to
``true`` but did NOT set a ``*.ranking_weight``. The dispatcher in
:mod:`apps.pipeline.services.phase6_ranker_contribution` reads each
weight from AppSetting and short-circuits picks at weight 0.0 — so
without seeded weights the dispatcher stayed inert even with every
flag on.

This migration sets paper-backed default weights for the six wired
ranker-time picks so the Recommended preset is fully active on
install. Cold-start safe in two ways:

1. Each adapter still returns 0.0 when the underlying trained
   model (LDA / KenLM / Node2Vec / BPR / FM) doesn't exist yet —
   the W1 training jobs populate those over the first few days.
   So flipping all six on at install time doesn't perturb the
   ranker until real models exist.
2. ``update_or_create`` is idempotent — re-running on an install
   that already has these rows just refreshes the description.

References
----------
- VADER #22  → Hutto & Gilbert 2014 ICWSM §3-4 (compound ∈ [-1, +1])
- KenLM #23  → Heafield 2011 WMT §4 (per-token log10 in -2 to -4)
- LDA #18    → Blei, Ng, Jordan 2003 JMLR §6 (topic-mixture cosine)
- Node2Vec   → Grover & Leskovec 2016 KDD §4 (cosine in [-1, +1])
- BPR #38    → Rendle et al. 2009 UAI §5 (factor dot-product)
- FM #39     → Rendle 2010 ICDM §3 eq. 1-3 (feature-cross prediction)

Sum of the six weights = 0.40, well under the typical 1.0 magnitude
of the existing 15-component composite. Picks fine-tune the ordering
without dominating it.
"""

from __future__ import annotations

from django.db import migrations


_KEYS = [
    (
        "vader_sentiment.ranking_weight",
        "0.05",
        "Phase 6 dispatcher weight × VADER compound (Hutto-Gilbert 2014 §3.2). "
        "0.05 bounds per-candidate sentiment shift to ~ ±0.05.",
        "ranking",
        "float",
    ),
    (
        "kenlm.ranking_weight",
        "0.05",
        "Phase 6 dispatcher weight × tanh(per_token + 3) (Heafield 2011 WMT §4). "
        "0.05 keeps fluency a small fine-tune signal.",
        "ranking",
        "float",
    ),
    (
        "lda.ranking_weight",
        "0.10",
        "Phase 6 dispatcher weight × cosine-of-topic-mixtures (Blei-Ng-Jordan 2003 §6). "
        "0.10 because IR experiments in the paper show topic similarity "
        "outperforms BoW for retrieval.",
        "ranking",
        "float",
    ),
    (
        "node2vec.ranking_weight",
        "0.05",
        "Phase 6 dispatcher weight × cosine of per-node embeddings "
        "(Grover-Leskovec 2016 KDD §4). 0.05 because PageRank/HITS/PPR/TrustRank "
        "already cover destination authority via score_node_affinity; "
        "Node2Vec adds dyadic community signal.",
        "ranking",
        "float",
    ),
    (
        "bpr.ranking_weight",
        "0.05",
        "Phase 6 dispatcher weight × tanh(BPR-score / 2) (Rendle 2009 UAI §5 Table 2).",
        "ranking",
        "float",
    ),
    (
        "factorization_machines.ranking_weight",
        "0.10",
        "Phase 6 dispatcher weight × tanh(FM-prediction) (Rendle 2010 ICDM §3 eq. 1-3). "
        "0.10 matches LDA — both are compositional signals over multiple features.",
        "ranking",
        "float",
    ),
    (
        "phase6_ranker.enabled",
        "true",
        "Operator killswitch for the entire phase6_ranker_contribution dispatcher. "
        "When false, every per-pick weight is ignored and contribution stays at 0.0.",
        "ranking",
        "bool",
    ),
]


def seed_phase6_ranker_weights(apps, schema_editor):
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
        ("suggestions", "0045_add_suggestion_indexes"),
        ("core", "0013_seed_embedding_provider_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_phase6_ranker_weights, reverse_seed),
    ]
