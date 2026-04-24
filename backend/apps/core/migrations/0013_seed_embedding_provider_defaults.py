"""Seed the AppSetting rows required by the embedding-provider system.

Runs automatically on every ``docker compose exec backend python manage.py
migrate``, so noob installs do not need a Django shell session to configure
providers, budgets, gate thresholds, or audit settings. Idempotent — each row
is ``get_or_create``d so re-running never overwrites values the operator has
edited in the Embeddings page.

Keys seeded here are consumed by:
  * apps/pipeline/services/embedding_providers/  (Part 1)
  * apps/pipeline/services/embedding_quality_gate.py  (Part 9)
  * apps/pipeline/services/embedding_audit.py  (Part 3)
  * apps/pipeline/services/embedding_bakeoff.py  (Part 4)
  * apps/pipeline/services/hardware_profile.py  (Part 8a)
  * apps/pipeline/services/embeddings.py  (graceful fallback, Part 8b)
"""

from __future__ import annotations

from django.db import migrations


# (key, value, value_type, category, description, is_secret)
_DEFAULT_ROWS: list[tuple[str, str, str, str, str, bool]] = [
    # Provider routing
    (
        "embedding.provider",
        "local",
        "str",
        "ml",
        "Active embedding provider: 'local', 'openai', or 'gemini'. Switch via the Embeddings page.",
        False,
    ),
    (
        "embedding.fallback_provider",
        "local",
        "str",
        "ml",
        "Provider to switch to when the active provider returns auth/rate-limit/budget errors.",
        False,
    ),
    (
        "embedding.recommended_provider",
        "",
        "str",
        "ml",
        "Winner of the last bake-off run (surfaced as a recommendation; never auto-applied).",
        False,
    ),
    # Provider configuration
    (
        "embedding.model",
        "BAAI/bge-m3",
        "str",
        "ml",
        "Model name for the active provider. Examples: 'BAAI/bge-m3' (local), 'text-embedding-3-small' (openai), 'text-embedding-004' (gemini).",
        False,
    ),
    (
        "embedding.api_key",
        "",
        "str",
        "api",
        "API key for the active remote provider. Never committed — encrypted at rest via is_secret=True.",
        True,
    ),
    (
        "embedding.api_base",
        "",
        "str",
        "api",
        "Optional base URL override (e.g. Azure OpenAI endpoint). Empty uses the provider default.",
        False,
    ),
    (
        "embedding.dimensions_override",
        "",
        "str",
        "ml",
        "Truncate embeddings to this dimension (OpenAI supports server-side truncation). Empty keeps the model default.",
        False,
    ),
    (
        "embedding.rate_limit_rpm",
        "3000",
        "int",
        "performance",
        "Requests-per-minute ceiling for API providers. Enforced client-side by the provider wrapper.",
        False,
    ),
    (
        "embedding.rate_limit_tpm",
        "1000000",
        "int",
        "performance",
        "Tokens-per-minute ceiling for API providers.",
        False,
    ),
    (
        "embedding.monthly_budget_usd",
        "50.0",
        "float",
        "performance",
        "Monthly spend cap across all API embedding calls. Exceeding this raises BudgetExceededError, which triggers the graceful fallback to local.",
        False,
    ),
    (
        "embedding.timeout_seconds",
        "30",
        "int",
        "performance",
        "HTTP request timeout for API providers.",
        False,
    ),
    (
        "embedding.max_retries",
        "5",
        "int",
        "performance",
        "Exponential-backoff retries on 429/5xx/timeout before giving up.",
        False,
    ),
    # Quality gate (Part 9)
    (
        "embedding.gate_enabled",
        "true",
        "bool",
        "ml",
        "Master toggle for the measure-twice-convinced-once replacement gate. Leave on unless debugging.",
        False,
    ),
    (
        "embedding.gate_quality_delta_threshold",
        "-0.05",
        "float",
        "ml",
        "Reject replacement when (new_provider_rank - old_provider_rank) < this. Protects against regressions.",
        False,
    ),
    (
        "embedding.gate_noop_cosine_threshold",
        "0.9999",
        "float",
        "ml",
        "Cosine similarity above this means new ≈ old; skip the write (NOOP).",
        False,
    ),
    (
        "embedding.gate_stability_threshold",
        "0.99",
        "float",
        "ml",
        "Re-sample cosine below this means the provider's output is unstable; reject.",
        False,
    ),
    (
        "embedding.provider_ranking_json",
        "{}",
        "json",
        "ml",
        "Provider-quality ranking map (signature -> NDCG). Written by the bake-off task; consumed by the gate.",
        False,
    ),
    # Audit (Part 3)
    (
        "embedding.accuracy_check_enabled",
        "true",
        "bool",
        "ml",
        "Master toggle for the fortnightly embedding-accuracy audit.",
        False,
    ),
    (
        "embedding.audit_resample_size",
        "50",
        "int",
        "ml",
        "How many healthy-looking items to re-embed per audit run for drift detection.",
        False,
    ),
    (
        "embedding.audit_norm_tolerance",
        "0.02",
        "float",
        "ml",
        "Acceptable deviation from unit-norm 1.0; outside this band the vector is flagged drift_norm.",
        False,
    ),
    (
        "embedding.audit_drift_threshold",
        "0.9999",
        "float",
        "ml",
        "Minimum cosine between stored and re-embedded vector; below this the item is flagged drift_resample.",
        False,
    ),
    (
        "embedding.accuracy_last_run_at",
        "",
        "str",
        "ml",
        "ISO timestamp of the last successful audit run (used for the 13-day fortnight gate).",
        False,
    ),
    # Bake-off (Part 4)
    (
        "embedding.bakeoff_enabled",
        "true",
        "bool",
        "ml",
        "Master toggle for the monthly provider bake-off.",
        False,
    ),
    (
        "embedding.bakeoff_sample_size",
        "1000",
        "int",
        "ml",
        "Number of approved (positive) pairs sampled per bake-off run.",
        False,
    ),
    (
        "embedding.bakeoff_cost_cap_usd",
        "5.0",
        "float",
        "performance",
        "Per-run USD cap for a single bake-off; aborts before starting if estimated cost exceeds this.",
        False,
    ),
    # Hardware auto-tune (Part 8a)
    (
        "performance.profile_override",
        "",
        "str",
        "performance",
        "Force a hardware tier for testing: 'low', 'medium', 'high', 'workstation'. Empty auto-detects.",
        False,
    ),
]


def seed_embedding_defaults(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for key, value, value_type, category, description, is_secret in _DEFAULT_ROWS:
        AppSetting.objects.get_or_create(
            key=key,
            defaults={
                "value": value,
                "value_type": value_type,
                "category": category,
                "description": description,
                "is_secret": is_secret,
            },
        )


def reverse_seed(apps, schema_editor):
    # Reverse is a no-op: we deliberately do not delete operator edits.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_useractivity_passkeychallenge_passkeycredential"),
    ]

    operations = [
        migrations.RunPython(seed_embedding_defaults, reverse_code=reverse_seed),
    ]
