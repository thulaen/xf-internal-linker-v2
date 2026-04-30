"""Seed AppSetting defaults for Harmonious-12 Group G signals.

Includes Aho-Corasick phrase matching, lemmatization, and NLP-driven boosts
(noun chunks, lexical richness, fuzzy matches, phonetic alignment, JSD).
These values match the researched starting points in recommended_weights.py.
"""

from __future__ import annotations
from django.db import migrations

_KEYS = [
    (
        "phrase_matching.ranking_weight",
        "0.08",
        "Weight for the phrase-matching signal. High-performance Aho-Corasick implementation (pick #56).",
        "ranking",
        "float",
    ),
    (
        "phrase_matching.enable_anchor_expansion",
        "true",
        "When true, matches anchor phrases found in the host sentence against the destination content.",
        "ranking",
        "bool",
    ),
    (
        "phrase_matching.enable_partial_matching",
        "true",
        "Enables partial/sub-phrase matching for anchors (longest contiguous overlap).",
        "ranking",
        "bool",
    ),
    (
        "phrase_matching.enable_lemma_matching",
        "true",
        "Enables matching on lemmatized tokens (requires spacy).",
        "ranking",
        "bool",
    ),
    (
        "phrase_matching.noun_chunk_boost_weight",
        "0.05",
        "Additive boost for anchors that exactly match a noun chunk in the host sentence (pick #55).",
        "ranking",
        "float",
    ),
    (
        "phrase_matching.fuzzy_match_weight",
        "0.08",
        "Additive weight for fuzzy lexical alignment between anchor and destination (pick #62).",
        "ranking",
        "float",
    ),
    (
        "phrase_matching.jsd_boost_weight",
        "0.10",
        "Additive boost for low Jensen-Shannon Divergence between host and destination tokens (pick #64).",
        "ranking",
        "float",
    ),
    (
        "phrase_matching.lexical_richness_weight",
        "0.05",
        "Additive boost for host sentences with high TTR/lexical richness (pick #57).",
        "ranking",
        "float",
    ),
    (
        "phrase_matching.phonetic_boost_weight",
        "0.04",
        "Additive boost for phonetic key overlap (Double Metaphone) between host and destination (pick #61).",
        "ranking",
        "float",
    ),
    (
        "phrase_matching.context_window_tokens",
        "8",
        "Number of surrounding tokens to consider as context for the anchor match.",
        "ranking",
        "int",
    ),
    (
        "lemma.enabled",
        "true",
        "Master switch for lemmatization infrastructure (pick #54).",
        "ranking",
        "bool",
    ),
]

def seed_group_g_defaults(apps, schema_editor):
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
    keys_to_remove = [k for k, *_ in _KEYS]
    AppSetting.objects.filter(key__in=keys_to_remove).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0056_add_char_ngram_vector_to_contentitem"),
        ("core", "0013_seed_embedding_provider_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_group_g_defaults, reverse_seed),
    ]
