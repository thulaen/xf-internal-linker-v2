"""Seed AppSetting rows for the 10 Phase 6 / Wire-phase optional picks.

Idempotent ``update_or_create`` upserts so re-running this migration
on an installation that already has these rows just refreshes the
descriptions. Each value is the spec-backed default cited in the
recommended_weights.py block — no surprise values, no orphan keys.
"""

from __future__ import annotations

from django.db import migrations


_KEYS = [
    # ── Pick #22 VADER (Hutto & Gilbert 2014 ICWSM) ────────────────
    (
        "vader_sentiment.enabled",
        "true",
        "Pick #22 VADER sentiment master switch. Source: Hutto & Gilbert (2014) ICWSM.",
        "ranking",
        "bool",
    ),
    # ── Pick #15 PySBD (Sadvilkar & Neumann 2020 ACL Demos) ────────
    (
        "pysbd_segmenter.enabled",
        "true",
        "Pick #15 PySBD sentence-boundary master switch. Source: Sadvilkar & Neumann (2020) ACL Demos.",
        "parse",
        "bool",
    ),
    (
        "pysbd_segmenter.language",
        "en",
        "Pick #15 PySBD language code. ``en`` matches the corpus.",
        "parse",
        "str",
    ),
    # ── Pick #17 YAKE! (Campos et al. 2020 Inf. Sci. §3.5) ─────────
    (
        "yake_keywords.enabled",
        "true",
        "Pick #17 YAKE! master switch. Source: Campos et al. (2020) Inf. Sci.",
        "parse",
        "bool",
    ),
    (
        "yake_keywords.ngram_max",
        "3",
        "Pick #17 YAKE! n-gram max. 3 = trigrams (paper §3.5).",
        "parse",
        "int",
    ),
    (
        "yake_keywords.dedup_threshold",
        "0.9",
        "Pick #17 YAKE! Levenshtein-distance deduplication threshold (paper §3.5).",
        "parse",
        "float",
    ),
    (
        "yake_keywords.top_k",
        "20",
        "Pick #17 YAKE! top-K keywords per document (paper baseline 5-20).",
        "parse",
        "int",
    ),
    (
        "yake_keywords.language",
        "en",
        "Pick #17 YAKE! language code.",
        "parse",
        "str",
    ),
    # ── Pick #7 Trafilatura (Barbaresi 2021 ACL Demos) ─────────────
    (
        "trafilatura_extractor.enabled",
        "true",
        "Pick #7 Trafilatura master switch. Source: Barbaresi (2021) ACL Demos.",
        "ingest",
        "bool",
    ),
    (
        "trafilatura_extractor.favor_recall",
        "false",
        "Pick #7 Trafilatura precision-vs-recall profile. False = precision (paper recommended for NLP).",
        "ingest",
        "bool",
    ),
    (
        "trafilatura_extractor.include_comments",
        "false",
        "Pick #7 Trafilatura: skip comments (XF threading captures replies separately).",
        "ingest",
        "bool",
    ),
    (
        "trafilatura_extractor.include_tables",
        "true",
        "Pick #7 Trafilatura: keep tables (resource pages carry tabular signal).",
        "ingest",
        "bool",
    ),
    # ── Pick #14 FastText LangID (Joulin et al. 2016 EACL §3) ─────
    (
        "fasttext_langid.enabled",
        "true",
        "Pick #14 FastText LangID master switch. Source: Joulin et al. (2016) EACL.",
        "parse",
        "bool",
    ),
    (
        "fasttext_langid.model_path",
        "/opt/models/lid.176.bin",
        "Pick #14 FastText LangID model path. Downloaded by the Dockerfile.",
        "parse",
        "str",
    ),
    (
        "fasttext_langid.min_confidence",
        "0.4",
        "Pick #14 FastText LangID confidence floor. Below this returns UND. Joulin reports ~0.998 mean on clean inputs; 0.4 catches noisy posts.",
        "parse",
        "float",
    ),
    # ── Pick #18 LDA (Blei, Ng, Jordan 2003 JMLR §6) ──────────────
    (
        "lda.enabled",
        "true",
        "Pick #18 LDA master switch. Source: Blei, Ng & Jordan (2003) JMLR.",
        "parse",
        "bool",
    ),
    (
        "lda.num_topics",
        "50",
        "Pick #18 LDA topic count. 50 = small-corpus default (paper §6 used 100 on Wikipedia).",
        "parse",
        "int",
    ),
    (
        "lda.passes",
        "5",
        "Pick #18 LDA training passes (gensim documented good-enough default).",
        "parse",
        "int",
    ),
    (
        "lda.alpha",
        "auto",
        "Pick #18 LDA Dirichlet prior on topics (gensim auto-infers).",
        "parse",
        "str",
    ),
    (
        "lda.eta",
        "auto",
        "Pick #18 LDA Dirichlet prior on words (gensim auto-infers).",
        "parse",
        "str",
    ),
    (
        "lda.model_path",
        "/app/media/lda/lda.model",
        "Pick #18 LDA model file (written by W1 lda_topic_refresh).",
        "parse",
        "str",
    ),
    (
        "lda.dictionary_path",
        "/app/media/lda/lda.dict",
        "Pick #18 LDA gensim Dictionary file.",
        "parse",
        "str",
    ),
    # ── Pick #23 KenLM (Heafield 2011 WMT) ────────────────────────
    (
        "kenlm.enabled",
        "true",
        "Pick #23 KenLM master switch. Source: Heafield (2011) WMT.",
        "parse",
        "bool",
    ),
    (
        "kenlm.order",
        "3",
        "Pick #23 KenLM n-gram order. 3 = trigram (paper headline benchmark).",
        "parse",
        "int",
    ),
    (
        "kenlm.model_path",
        "/app/media/kenlm/model.arpa",
        "Pick #23 KenLM ARPA model file (written by W1 kenlm_retrain via lmplz).",
        "parse",
        "str",
    ),
    # ── Pick #37 Node2Vec (Grover & Leskovec 2016 KDD §4 Table 1) ──
    (
        "node2vec.enabled",
        "true",
        "Pick #37 Node2Vec master switch. Source: Grover & Leskovec (2016) KDD.",
        "ranking",
        "bool",
    ),
    (
        "node2vec.dimensions",
        "64",
        "Pick #37 Node2Vec embedding dimension (paper Table 1).",
        "ranking",
        "int",
    ),
    (
        "node2vec.walk_length",
        "30",
        "Pick #37 Node2Vec random-walk length per starting node (paper Table 1).",
        "ranking",
        "int",
    ),
    (
        "node2vec.num_walks",
        "200",
        "Pick #37 Node2Vec walks per node (paper Table 1).",
        "ranking",
        "int",
    ),
    (
        "node2vec.p",
        "1.0",
        "Pick #37 Node2Vec return parameter p (1.0 = balanced).",
        "ranking",
        "float",
    ),
    (
        "node2vec.q",
        "1.0",
        "Pick #37 Node2Vec in-out parameter q (1.0 = balanced).",
        "ranking",
        "float",
    ),
    (
        "node2vec.window",
        "10",
        "Pick #37 Node2Vec Word2Vec window size (paper §4.1).",
        "ranking",
        "int",
    ),
    (
        "node2vec.embeddings_path",
        "/app/media/node2vec/embeddings.pkl",
        "Pick #37 Node2Vec persisted embeddings (W1 node2vec_walks).",
        "ranking",
        "str",
    ),
    # ── Pick #38 BPR (Rendle et al. 2009 UAI §5 Table 2) ──────────
    (
        "bpr.enabled",
        "true",
        "Pick #38 BPR master switch. Source: Rendle, Freudenthaler, Gantner & Schmidt-Thieme (2009) UAI.",
        "ranking",
        "bool",
    ),
    (
        "bpr.factors",
        "50",
        "Pick #38 BPR latent-factor count (paper Table 2).",
        "ranking",
        "int",
    ),
    (
        "bpr.iterations",
        "100",
        "Pick #38 BPR training iterations (paper Table 2).",
        "ranking",
        "int",
    ),
    (
        "bpr.learning_rate",
        "0.01",
        "Pick #38 BPR learning rate α (paper Table 2).",
        "ranking",
        "float",
    ),
    (
        "bpr.regularization",
        "0.01",
        "Pick #38 BPR regularisation λ (paper Table 2).",
        "ranking",
        "float",
    ),
    (
        "bpr.model_path",
        "/app/media/bpr/model.pkl",
        "Pick #38 BPR persisted model + indexes (W1 bpr_refit).",
        "ranking",
        "str",
    ),
    # ── Pick #39 FM (Rendle 2010 ICDM §3.1) ───────────────────────
    (
        "factorization_machines.enabled",
        "true",
        "Pick #39 FM master switch. Source: Rendle (2010) ICDM.",
        "ranking",
        "bool",
    ),
    (
        "factorization_machines.factors",
        "8",
        "Pick #39 FM latent-factor count (paper §3.1 small-feature default).",
        "ranking",
        "int",
    ),
    (
        "factorization_machines.num_iter",
        "50",
        "Pick #39 FM training iterations (paper §3.1).",
        "ranking",
        "int",
    ),
    (
        "factorization_machines.learning_rate",
        "0.001",
        "Pick #39 FM SGD learning rate (paper §3.1 stable-convergence recommendation).",
        "ranking",
        "float",
    ),
    (
        "factorization_machines.model_path",
        "/app/media/fm/model.pkl",
        "Pick #39 FM persisted model + DictVectorizer (W1 factorization_machines_refit).",
        "ranking",
        "str",
    ),
]


def seed_phase6_defaults(apps, schema_editor):
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
        ("suggestions", "0042_suggestion_impression"),
        # Depend on the latest core migration at the time this seed
        # was written. Pinning to 0001_initial would break safe
        # rollback (core 0001 → 0013 → 0001 would orphan this seed).
        ("core", "0013_seed_embedding_provider_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_phase6_defaults, reverse_seed),
    ]
