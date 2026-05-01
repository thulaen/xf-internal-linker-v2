"""Phase 0.12 — purge stale ``http_worker`` ServiceStatusSnapshot rows.

The C# HTTP-worker service was decommissioned 2026-04-12 (ISS-009). Code
paths (REST view + realtime signals) suppress any row with
``service_name="http_worker"`` so the System Health page does not show it.
But operators with DBs that pre-date the suppression still have a stale
``http_worker`` row sitting in ``ServiceStatusSnapshot`` and have reported
that it intermittently flashes on the System Health page if any cached
or admin view bypasses the suppression filter.

This migration is the durable fix: delete the row(s) entirely. Idempotent —
a fresh DB or a DB whose row was already cleared has nothing to do. The
``http_worker`` choice key stays in ``ServiceStatusSnapshot.SERVICE_NAMES``
so future migrations don't fail on a missing-choice error if a third-party
script tries to reinsert one (it would be deleted on the next migrate
anyway).
"""

from django.db import migrations


def purge_http_worker_rows(apps, schema_editor):
    ServiceStatusSnapshot = apps.get_model("diagnostics", "ServiceStatusSnapshot")
    deleted, _ = ServiceStatusSnapshot.objects.filter(service_name="http_worker").delete()
    if deleted:
        print(
            f"\n-- Migration 0004: purged {deleted} stale http_worker "
            f"ServiceStatusSnapshot row(s) (ISS-009 cleanup)."
        )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("diagnostics", "0003_relabel_decommissioned_services"),
    ]
    operations = [
        migrations.RunPython(purge_http_worker_rows, noop_reverse),
    ]
