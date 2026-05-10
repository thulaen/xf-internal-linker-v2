"""Dedup OperationEvent.dedup_key + add partial unique constraint.

Closes AutoIssue #10 + RPT-004 row 3 (NO-DUPLICATES.md invariant).

The 2026-05-10 audit found 1,491 duplicate `dedup_key` values across
2,012 rows (only 521 distinct keys). Without enforcement, every dedup
write was getting a fresh PK so the table grew unbounded.

This migration:
  1. **Forward** — for each duplicate dedup_key (non-blank), keeps the
     LATEST row (highest pk by timestamp) and deletes the older copies.
     Blank dedup_keys are exempt (legacy rows without a hash).
  2. **Forward (cont.)** — adds a partial UniqueConstraint on
     `dedup_key WHERE dedup_key != ''` so future writes can't reintroduce
     duplicates.
  3. **Reverse** — only drops the constraint. The dedup'd rows are NOT
     restored on rollback (we don't keep their content).
"""
from __future__ import annotations

from django.db import migrations, models


def _dedup_operation_events(apps, schema_editor) -> None:
    """Keep the latest row per non-blank dedup_key; delete the rest."""
    OperationEvent = apps.get_model("ops_feed", "OperationEvent")
    # Collect every dedup_key that has duplicates.
    from django.db.models import Count

    dup_keys = (
        OperationEvent.objects.exclude(dedup_key="")
        .exclude(dedup_key__isnull=True)
        .values("dedup_key")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .values_list("dedup_key", flat=True)
    )
    deleted_total = 0
    for dedup_key in dup_keys:
        rows = list(
            OperationEvent.objects.filter(dedup_key=dedup_key)
            .order_by("-timestamp", "-pk")
            .values_list("pk", flat=True)
        )
        if len(rows) <= 1:
            continue
        # Keep rows[0] (latest); delete rows[1:].
        deleted, _ = OperationEvent.objects.filter(pk__in=rows[1:]).delete()
        deleted_total += deleted
    print(f"[ops_feed.0002] dedup'd {deleted_total} duplicate OperationEvent rows across {len(list(dup_keys))} dedup_keys")  # print-allowed: data-migration progress


def _noop_reverse(apps, schema_editor) -> None:
    """Reverse is a no-op — we don't restore deleted rows."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ops_feed", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_dedup_operation_events, _noop_reverse),
        migrations.AddConstraint(
            model_name="operationevent",
            constraint=models.UniqueConstraint(
                fields=("dedup_key",),
                condition=~models.Q(dedup_key=""),
                name="unique_operation_event_dedup_key",
            ),
        ),
    ]
