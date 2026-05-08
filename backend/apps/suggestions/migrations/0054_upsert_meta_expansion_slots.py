"""Upsert the expanded meta-algorithm slots (META-40..META-249) into AppSetting.

This ensures the registry-driven Settings UI and the auto-tuner have access
to all forward-declared slots. Every slot is seeded as enabled=false and
weight=0.00.
"""

from __future__ import annotations
from django.db import migrations


def upsert_expansion_slots(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")

    # We use a helper dict to simulate the expansion file contents
    # so we don't have to list 420 keys in this migration file.
    # Matches the structure in recommended_weights_forward_249.py.

    # Block P1..P8 — Specific Research-backed slots
    specific_prefixes = [
        "newton",
        "lbfgs",
        "conjugate_gradient",
        "lbfgs_b",
        "simulated_annealing",
        "genetic_opt",
        "differential_evolution",
        "pso",
        "nelder_mead",
        "cma_es",
        "ranknet",
        "lambdarank",
        "lambdamart",
        "listnet",
        "rankboost",
        "tpe",
        "coordinate_ascent",
        "boltzmann_ranker",
        "softrank",
        "svm_rank",
        "glove",
        "fasttext_embeddings",
        "elmo",
        "bert",
        "roberta",
        "albert",
        "distilbert",
        "t5",
        "gpt2",
        "clip",
        "hits_hubs",
        "salsa",
        "eigentrust",
        "simrank",
        "pathsim",
        "deepwalk",
        "graphsage",
        "lambdaloss",
        "gcn",
        "gat",
        "isotonic_calibration",
        "temperature_scaling",
        "dirichlet_calibration",
        "beta_calibration",
        "venn_abers",
        "mc_dropout",
        "deep_ensembles",
        "platt_scaling",
        "conformal_inductive",
        "conformal_transductive",
        "weight_decay",
        "cosine_annealing",
        "lasso",
        "elastic_net",
        "batch_norm",
        "layer_norm",
        "swa",
        "label_smoothing",
        "dropconnect",
        "early_stopping",
        "smote",
        "adasyn",
        "ohem",
        "reservoir_sampling",
        "importance_sampling",
        "stratified_sampling",
        "downsampling",
        "bagging",
        "boosting",
        "cross_validation",
        "demographic_parity",
        "equalized_odds",
        "disparate_impact",
        "counterfactual_fairness",
        "individual_fairness",
        "group_fairness",
        "group_calibration",
        "rejection_option",
        "fair_preproc",
        "adversarial_debiasing",
    ]

    for prefix in specific_prefixes:
        AppSetting.objects.get_or_create(
            key=f"{prefix}.enabled",
            defaults={
                "value": "false",
                "value_type": "bool",
                "category": "ml",
                "description": f"Forward-declared slot for {prefix.replace('_', ' ')} (META-NN).",
            },
        )
        AppSetting.objects.get_or_create(
            key=f"{prefix}.ranking_weight",
            defaults={
                "value": "0.00",
                "value_type": "float",
                "category": "ml",
                "description": f"Ranking weight for {prefix.replace('_', ' ')} (META-NN).",
            },
        )

    # Generic slots 120..249
    for i in range(120, 250):
        prefix = f"meta_slot_{i}"
        AppSetting.objects.get_or_create(
            key=f"{prefix}.enabled",
            defaults={
                "value": "false",
                "value_type": "bool",
                "category": "ml",
                "description": f"Forward-declared generic expansion slot (META-{i}).",
            },
        )
        # Note: Generic slots don't strictly need weight keys until activated,
        # but we add them for uniformity so enumerate_metas() finds them.
        AppSetting.objects.get_or_create(
            key=f"{prefix}.ranking_weight",
            defaults={
                "value": "0.00",
                "value_type": "float",
                "category": "ml",
                "description": f"Ranking weight for generic slot (META-{i}).",
            },
        )


def reverse_upsert(apps, schema_editor):
    pass  # No-op to avoid accidental data loss on rollback


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0053_seed_quick_controls_setting"),
        ("core", "0013_seed_embedding_provider_defaults"),
    ]

    operations = [
        migrations.RunPython(upsert_expansion_slots, reverse_upsert),
    ]
