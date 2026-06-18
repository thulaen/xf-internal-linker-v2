"""Celery task: automated provider bake-off (plan Part 4, FR-232).

Runs on the ``pipeline`` queue. Iterates every configured paid provider,
scores them against the user's approved /
rejected Suggestion history, and writes an ``EmbeddingBakeoffResult`` row per
provider. Updates ``embedding.provider_ranking_json`` so the quality gate
(Part 9) can consume it immediately.

Resilience:
  * Unique ``(job_id, provider)`` constraint → resume-safe.
  * Each provider runs independently; one provider's failure (missing API key,
    budget) logs a warning and moves on to the next.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import connection

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="pipeline.embedding_provider_bakeoff",
    queue="pipeline",
    soft_time_limit=60 * 60,
    time_limit=60 * 60 + 300,
    max_retries=0,
)
@HelperConstraint(
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=4000,
    expected_seconds_p50=1800,
)
def embedding_provider_bakeoff(
    self, *, sample_size: int | None = None, providers: list[str] | None = None
):
    """Score every configured provider on approved/rejected qrels."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.core.models import AppSetting
    from apps.pipeline.services.embedding_bakeoff import (
        apply_provider_verdicts,
        load_texts,
        persist_run,
        sample_ground_truth,
        score_provider,
        update_provider_ranking,
    )
    from apps.pipeline.services.embedding_providers import clear_cache, get_provider

    # Read default sample size if not explicitly supplied.
    # Group D consolidation (2026-04-28): single call to the shared
    # ``AppSetting.get_int`` helper.
    if sample_size is None:
        sample_size = AppSetting.get_int("embedding.bakeoff_sample_size", 1000)

    positives, negatives = sample_ground_truth(sample_size=sample_size)
    if not positives:
        logger.info("bakeoff: no approved pairs; skipping run")
        return {"skipped": "no_positives"}

    # Load texts + pre-load stored vectors for the destination pool so we can
    # reuse them across providers (stored vectors belong to whoever embedded
    # them last — the bake-off evaluates each provider by re-embedding).
    pool_ids = {d for _, d in positives} | {d for _, d in negatives}
    host_ids = {h for h, _ in positives} | {h for h, _ in negatives}
    texts = load_texts(pool_ids | host_ids)

    provider_bans = _provider_bans()
    providers_to_test = [
        provider for provider in providers or _discover_providers() if provider not in provider_bans
    ]
    # Group D consolidation: snapshot the operator's chosen provider
    # via the shared helper. Default "local" matches the existing
    # fallback when the AppSetting row doesn't exist yet.
    original_value = AppSetting.get_str("embedding.provider", "local") or "local"
    results = _score_providers(
        job_id=self.request.id,
        providers_to_test=providers_to_test,
        original_value=original_value,
        positives=positives,
        negatives=negatives,
        texts=texts,
    )
    apply_provider_verdicts(
        results,
        champion_provider=original_value,
        existing_loss_counts=_provider_loss_counts(),
    )
    for run in results:
        persist_run(job_id=self.request.id, run=run)
    _persist_provider_bans(results)
    update_provider_ranking(results)
    return {"providers_scored": len(results)}


def _score_providers(
    *,
    job_id: str,
    providers_to_test: list[str],
    original_value: str,
    positives: list,
    negatives: list,
    texts: dict,
) -> list:
    from apps.core.models import AppSetting
    from apps.pipeline.services.embedding_providers import clear_cache

    results = []
    try:
        for name in providers_to_test:
            AppSetting.objects.update_or_create(
                key="embedding.provider",
                defaults={"value": name},
            )
            clear_cache()
            run = _score_one_provider(
                name=name,
                job_id=job_id,
                positives=positives,
                negatives=negatives,
                texts=texts,
            )
            if run is not None:
                results.append(run)
    finally:
        # Restore original provider selection so the pipeline keeps behaving
        # the same after the bake-off finishes.
        AppSetting.objects.update_or_create(
            key="embedding.provider",
            defaults={"value": original_value},
        )
        clear_cache()
    return results


def _score_one_provider(
    *,
    name: str,
    job_id: str,
    positives: list,
    negatives: list,
    texts: dict,
):
    from apps.pipeline.services.embedding_bakeoff import persist_run, score_provider
    from apps.pipeline.services.embedding_providers import get_provider

    try:
        provider = get_provider()
        try:
            provider.healthcheck()
        except Exception as hc_exc:
            logger.warning("bakeoff: %s healthcheck failed: %s", name, hc_exc)
            return None
        run = score_provider(
            provider=provider,
            positives=positives,
            negatives=negatives,
            texts=texts,
        )
        persist_run(job_id=job_id, run=run)
        _log_bakeoff_run(run)
        return run
    except Exception:
        logger.exception("bakeoff: provider %s failed", name)
        return None


def _log_bakeoff_run(run) -> None:
    logger.info(
        "bakeoff %s: mrr=%.4f ndcg=%.4f recall=%.4f cost=$%.4f",
        run.provider_name,
        run.mrr_at_10,
        run.ndcg_at_10,
        run.recall_at_10,
        run.cost_usd,
    )


def _discover_providers() -> list[str]:
    """Return provider names that have credentials configured."""
    from apps.core.models import AppSetting

    providers = ["local"]  # local is always available
    # Group D consolidation: shared ``get_str`` collapses the row-fetch
    # + null check + value-strip into one line.
    try:
        api_key = AppSetting.get_str("embedding.api_key", "").strip()
        if api_key:
            # A single API key field is provider-specific — we test both
            # OpenAI and Gemini; each provider's healthcheck will skip if the
            # key is not for that service.
            providers.extend(["openai", "gemini"])
    except Exception:  # noqa: BLE001
        logger.warning("bakeoff: provider discovery could not read settings", exc_info=True)
    return providers


def _provider_bans() -> set[str]:
    from apps.core.models import AppSetting

    try:
        import json

        raw_value = AppSetting.get_str("embedding.provider_bans_json", "[]")
        decoded = json.loads(raw_value or "[]")
    except Exception:
        logger.warning("bakeoff: provider ban list could not be read", exc_info=True)
        return set()
    if not isinstance(decoded, list):
        return set()
    return {str(provider).strip().lower() for provider in decoded if provider}


def _provider_loss_counts() -> dict[str, int]:
    from django.db.models import Max

    from apps.pipeline.models import EmbeddingBakeoffResult

    rows = (
        EmbeddingBakeoffResult.objects.values("provider")
        .annotate(losses=Max("loss_count"))
        .iterator(chunk_size=100)
    )
    return {str(row["provider"]): int(row["losses"] or 0) for row in rows}


def _persist_provider_bans(results) -> None:
    banned = sorted({run.provider_name for run in results if run.is_banned})
    if not banned:
        return
    import json

    from apps.core.models import AppSetting

    current = _provider_bans()
    current.update(banned)
    AppSetting.objects.update_or_create(
        key="embedding.provider_bans_json",
        defaults={"value": json.dumps(sorted(current))},
    )
