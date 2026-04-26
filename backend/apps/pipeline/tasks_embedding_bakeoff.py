"""Celery task: automated provider bake-off (plan Part 4, FR-232).

Runs on the ``pipeline`` queue. Iterates every configured provider (local +
optionally openai + gemini), scores them against the user's approved /
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

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="pipeline.embedding_provider_bakeoff",
    queue="pipeline",
    soft_time_limit=60 * 60,
    time_limit=60 * 60 + 300,
    max_retries=0,
)
def embedding_provider_bakeoff(self, *, sample_size: int | None = None, providers: list[str] | None = None):
    """Score every configured provider on approved/rejected qrels."""
    from apps.core.models import AppSetting
    from apps.pipeline.services.embedding_bakeoff import (
        load_texts,
        persist_run,
        sample_ground_truth,
        score_provider,
        update_provider_ranking,
    )
    from apps.pipeline.services.embedding_providers import clear_cache, get_provider

    # Read default sample size if not explicitly supplied.
    if sample_size is None:
        try:
            row = AppSetting.objects.filter(key="embedding.bakeoff_sample_size").first()
            sample_size = int(row.value) if row and row.value else 1000
        except Exception:
            sample_size = 1000

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

    providers_to_test = providers or _discover_providers()
    results = []
    original_setting = AppSetting.objects.filter(key="embedding.provider").first()
    original_value = original_setting.value if original_setting else "local"
    try:
        for name in providers_to_test:
            # Switch AppSetting so get_provider returns the one we want.
            AppSetting.objects.update_or_create(
                key="embedding.provider",
                defaults={"value": name},
            )
            clear_cache()
            try:
                provider = get_provider()
                # Verify credentials before spending API budget on a full run.
                try:
                    provider.healthcheck()
                except Exception as hc_exc:
                    logger.warning("bakeoff: %s healthcheck failed: %s", name, hc_exc)
                    continue
                run = score_provider(
                    provider=provider,
                    positives=positives,
                    negatives=negatives,
                    texts=texts,
                )
                persist_run(job_id=self.request.id, run=run)
                results.append(run)
                logger.info(
                    "bakeoff %s: mrr=%.4f ndcg=%.4f recall=%.4f cost=$%.4f",
                    run.provider_name,
                    run.mrr_at_10,
                    run.ndcg_at_10,
                    run.recall_at_10,
                    run.cost_usd,
                )
            except Exception:
                logger.exception("bakeoff: provider %s failed", name)
                continue
    finally:
        # Restore original provider selection so the pipeline keeps behaving
        # the same after the bake-off finishes.
        AppSetting.objects.update_or_create(
            key="embedding.provider",
            defaults={"value": original_value},
        )
        clear_cache()

    update_provider_ranking(results)
    return {"providers_scored": len(results)}


def _discover_providers() -> list[str]:
    """Return provider names that have credentials configured."""
    from apps.core.models import AppSetting

    providers = ["local"]  # local is always available
    try:
        api_key_row = AppSetting.objects.filter(key="embedding.api_key").first()
        if api_key_row and str(api_key_row.value).strip():
            # A single API key field is provider-specific — we test both
            # OpenAI and Gemini; each provider's healthcheck will skip if the
            # key is not for that service.
            providers.extend(["openai", "gemini"])
    except Exception:
        pass
    return providers
