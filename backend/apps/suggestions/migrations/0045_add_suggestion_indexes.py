"""Slice 4 — A.6 + A.7 Suggestion indexes for hot-path queries.

Three indexes added in one migration:

- ``sug_status_origin_idx`` — compound (status, candidate_origin)
  for the feedback_relevance + pipeline_data hot-path queries that
  filter on both columns. Postgres can't AND two single-column
  indexes; this compound one accelerates the typical "pending
  suggestions of source X" pattern.

- ``sug_updated_at_idx`` — supports the retention scans added in
  ``apps.pipeline.tasks.nightly_data_retention`` (B.5/B.7), the
  NDCG 30-day window scan in
  ``apps.pipeline.services.ndcg_eval``, and the future G3.1
  scope-content-signature compute. Without this, Postgres falls
  back to a sequential scan on every retention run.

- ``sug_status_updated_at_idx`` — compound (status, updated_at) is
  the most selective index for the B.7 prune query
  (``status__in=("pending", "stale"), updated_at__lt=cutoff``).
  Lets Postgres pick the right rows in O(log N) instead of an
  index merge.

Cost: three new B-tree indexes on the suggestions_suggestion
table. At our write rate (≤ 50 INSERTs/min during pipeline runs)
the write-amplification cost is negligible. Read wins on retention,
NDCG, and feedback queries.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0031_contentitem_pq_code_contentitem_pq_code_version'),
        ('suggestions', '0044_fasttext_path_to_opt'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='suggestion',
            index=models.Index(
                fields=['status', 'candidate_origin'],
                name='sug_status_origin_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='suggestion',
            index=models.Index(
                fields=['updated_at'],
                name='sug_updated_at_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='suggestion',
            index=models.Index(
                fields=['status', 'updated_at'],
                name='sug_status_updated_at_idx',
            ),
        ),
    ]
