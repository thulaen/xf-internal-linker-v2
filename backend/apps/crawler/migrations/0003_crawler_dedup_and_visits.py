"""Crawler dedup + per-visit log (masterplan Group D.5).

Three schema changes:

1. Composite index on ``(normalized_url, content_hash)`` for the new
   cross-session dedup lookup in ``_save_page_meta``. Without this
   the upsert would full-scan ``CrawledPageMeta`` on every crawled
   page; with it, the lookup is O(log N) on the typical 100k-page
   site. Storage cost: ~6 MB at 100k rows for a 64-char content_hash
   plus URL.

2. New ``CrawlerVisit`` model. One row per (session × deduplicated
   page) crawl event. Keeps a per-session audit trail without
   duplicating the heavy SEO snapshot every time the crawler revisits
   an unchanged URL.

3. No data migration. Existing ``CrawledPageMeta`` rows stay as-is;
   the new dedup behaviour kicks in for future crawls. The one-shot
   collapse of historical duplicates is a separate task (masterplan
   Group D.6) — kept in its own migration so this one stays a fast
   schema-only change that runs in seconds even on a multi-million
   row install.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crawler", "0002_crawlsession_frontier_snapshot_and_more"),
    ]

    operations = [
        # 1) Composite index for the dedup lookup.
        migrations.AddIndex(
            model_name="crawledpagemeta",
            index=models.Index(
                fields=["normalized_url", "content_hash"],
                name="crawled_page_url_hash_idx",
            ),
        ),
        # 2) The new per-visit log model.
        migrations.CreateModel(
            name="CrawlerVisit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "status_code",
                    models.SmallIntegerField(
                        default=200,
                        help_text="HTTP status returned during this specific visit.",
                    ),
                ),
                (
                    "content_hash",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Content hash observed at this visit. Same as "
                            "page_meta.content_hash for a normal visit; can be "
                            "empty for 304 conditional GET responses."
                        ),
                        max_length=64,
                    ),
                ),
                (
                    "visited_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="Wall-clock timestamp of the visit (auto-set).",
                    ),
                ),
                (
                    "page_meta",
                    models.ForeignKey(
                        help_text=(
                            "The (deduplicated) CrawledPageMeta row this visit observed."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="visits",
                        to="crawler.crawledpagemeta",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        help_text="The session during which this visit happened.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="visits",
                        to="crawler.crawlsession",
                    ),
                ),
            ],
            options={
                "verbose_name": "Crawler Visit",
                "verbose_name_plural": "Crawler Visits",
                "ordering": ["-visited_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="crawlervisit",
            constraint=models.UniqueConstraint(
                fields=("session", "page_meta"),
                name="unique_visit_per_session_page",
            ),
        ),
        migrations.AddIndex(
            model_name="crawlervisit",
            index=models.Index(
                fields=["page_meta", "-visited_at"],
                name="crawler_vis_page_me_aff345_idx",
            ),
        ),
    ]
