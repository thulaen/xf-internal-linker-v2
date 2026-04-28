"""One-shot collapse of historical cross-session CrawledPageMeta duplicates (Group D.6).

Plain-English purpose: before Group D.5 shipped, every full crawl
wrote a fresh ``CrawledPageMeta`` row per URL even when the page
body was unchanged from the previous crawl. This migration walks
through the table once, groups rows by ``(normalized_url, content_hash)``,
keeps the OLDEST row in each group as canonical, and deletes the
duplicates.

Safety guards:
  * Only collapses groups where both ``normalized_url`` AND ``content_hash``
    are non-empty. Rows with a missing hash (e.g. 304 conditional GET
    placeholders) are left alone.
  * Deletes the dupes one batch at a time inside a transaction so a
    huge backlog can't OOM the migration.
  * ``CrawledLink`` rows attached to deleted page-meta rows cascade-
    delete via the existing FK — this is the desired outcome since
    those links were extracted from the SAME body the canonical row
    also covers.
  * Idempotent: running twice is a no-op.
  * Non-reversible: ``reverse_code=noop``. The deleted rows can't be
    reconstructed because every duplicate was identical to the
    canonical by definition.
"""

from django.db import migrations, transaction
from django.db.models import Count, Min


def collapse_duplicates(apps, schema_editor):
    CrawledPageMeta = apps.get_model("crawler", "CrawledPageMeta")

    duplicate_groups = (
        CrawledPageMeta.objects.exclude(content_hash="")
        .exclude(normalized_url="")
        .values("normalized_url", "content_hash")
        .annotate(group_size=Count("id"), keeper_id=Min("id"))
        .filter(group_size__gt=1)
    )

    total_collapsed = 0
    batch: list[int] = []
    BATCH_SIZE = 500

    def flush_batch():
        nonlocal total_collapsed
        if not batch:
            return
        with transaction.atomic():
            deleted, _ = CrawledPageMeta.objects.filter(pk__in=batch).delete()
        total_collapsed += deleted
        batch.clear()

    for group in duplicate_groups.iterator(chunk_size=200):
        # Find every duplicate row in this group except the keeper.
        dupe_pks = list(
            CrawledPageMeta.objects.filter(
                normalized_url=group["normalized_url"],
                content_hash=group["content_hash"],
            )
            .exclude(pk=group["keeper_id"])
            .values_list("pk", flat=True)
        )
        batch.extend(dupe_pks)
        if len(batch) >= BATCH_SIZE:
            flush_batch()

    flush_batch()


class Migration(migrations.Migration):
    dependencies = [
        ("crawler", "0003_crawler_dedup_and_visits"),
    ]

    operations = [
        migrations.RunPython(
            collapse_duplicates,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
