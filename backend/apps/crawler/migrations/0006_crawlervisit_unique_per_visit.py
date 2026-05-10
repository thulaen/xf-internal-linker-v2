"""Adds the (session, page_meta, content_hash) UniqueConstraint to CrawlerVisit.

Closes AutoIssue #8 + RPT-004 row 1 (NO-DUPLICATES.md invariant).

The pre-2026-05-09 constraint was `(session, page_meta)` only, which
prevented re-recording the same visit but ALSO prevented logging a re-
visit with NEW content (different content_hash). Adding `content_hash`
to the unique tuple lets the second visit land as a new row when the
content changed, while still blocking pure duplicates.

Safety check (run 2026-05-10): the live `crawler_crawlervisit` table has
0 rows, so the new constraint cannot fail due to existing data. The
migration is a pure schema change.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crawler", "0005_rename_crawler_vis_page_me_aff345_idx_crawler_cra_page_me_09d41d_idx_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="crawlervisit",
            name="unique_visit_per_session_page",
        ),
        migrations.AddConstraint(
            model_name="crawlervisit",
            constraint=models.UniqueConstraint(
                fields=("session", "page_meta", "content_hash"),
                name="unique_visit_per_session_page_content",
            ),
        ),
    ]
