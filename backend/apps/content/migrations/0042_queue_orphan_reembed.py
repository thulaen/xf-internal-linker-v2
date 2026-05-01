"""Phase 0.0 — queue re-embed for orphan rows nulled by an earlier migration.

Why this migration exists
-------------------------
Migration ``0010_bge_m3_embedding_dim_1024`` legitimately nulls every
``ContentItem.embedding`` and ``Sentence.embedding`` row when the pgvector
dimension changes from 768 to 1024. Without an automatic re-embed step,
those rows stay NULL until something triggers the embed pipeline — which
silently degrades retrieval until the operator notices.

Any future schema change that nulls embeddings (different model, different
dim, different normalisation) inherits the same problem. This migration is
the durable catch-up: it queues the new ``reembed_null_embeddings`` Celery
task once, and the task walks every orphan in PK-checkpointed batches.

Idempotent: if no orphans exist, the task completes immediately. Safe to
re-run. Bounded: Celery picks up the work at its own pace; nothing is
processed inside the migration transaction itself.
"""

from django.db import migrations


def queue_reembed_for_orphans(apps, schema_editor):
    """Queue ``pipeline.reembed_null_embeddings`` if any ContentItems lost their embedding.

    Plain-English: count the rows whose embedding got cleared by a prior
    schema change. If there are any, ask Celery to refill them in the
    background. If the count is zero, do nothing.
    """
    ContentItem = apps.get_model("content", "ContentItem")

    orphan_count = ContentItem.objects.filter(
        embedding__isnull=True,
        is_deleted=False,
        duplicate_of__isnull=True,
    ).count()

    if orphan_count == 0:
        return

    print(
        f"\n-- Migration 0042: found {orphan_count} ContentItem rows with NULL "
        f"embedding (likely nulled by an earlier dim-change migration). "
        f"Queueing pipeline.reembed_null_embeddings to repopulate via the "
        f"existing BGE-M3 embed pipeline."
    )

    # Best-effort queue. If Celery is not available at migration time
    # (e.g. running migrate inside a build container with no broker),
    # print instructions instead of failing the migration.
    try:
        from apps.pipeline.tasks import reembed_null_embeddings

        reembed_null_embeddings.delay()
        print(
            "-- Migration 0042: task queued. Watch progress in Celery worker logs "
            "or via the dashboard."
        )
    except Exception as exc:
        print(
            f"-- Migration 0042: could not queue task ({exc}). "
            f"After migrate completes, run manually: "
            f"docker compose exec backend python manage.py shell -c "
            f"'from apps.pipeline.tasks import reembed_null_embeddings; "
            f"reembed_null_embeddings.delay()'"
        )


def noop_reverse(apps, schema_editor):
    """Reversing this migration is a no-op — Celery tasks cannot be un-queued."""
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0041_token"),
    ]
    operations = [
        migrations.RunPython(queue_reembed_for_orphans, noop_reverse),
    ]
