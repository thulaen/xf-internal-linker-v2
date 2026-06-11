"""Management command to resolve startup import error AutoIssues.

Resolves AutoIssues #22844, #23023, #23024 which were startup errors
captured by GlitchTip during the Python+Rust migration.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    """Resolve three startup import error AutoIssues."""

    help = "Resolve startup import error AutoIssues #22844, #23023, #23024"

    def handle(self, *args, **options):
        """Resolve the three startup issues."""
        # Resolve #22844: AutoIssue import error
        issue_22844 = AutoIssue.objects.get(id=22844)
        issue_22844.status = AutoIssue.STATUS_RESOLVED
        issue_22844.resolved_at = timezone.now()
        issue_22844.resolved_by = "auto-resolution"
        issue_22844.lessons_learned = (
            "Trap: During the Python+Rust migration, some startup initialization "
            "code tried to import AutoIssue from the wrong place (apps.audit.models "
            "instead of apps.auto_issues.models). This caused a startup ImportError "
            "when GlitchTip was initializing Django.\n\n"
            "Fix shape: Audited all imports of AutoIssue across the codebase and "
            "verified they all import from the correct location: apps.auto_issues.models. "
            "Added regression test in apps/api/test_startup_import_errors.py to ensure "
            "AutoIssue is never accidentally imported from apps.audit.models."
        )
        issue_22844.save(update_fields=[
            "status", "resolved_at", "resolved_by", "lessons_learned"
        ])
        self.stdout.write(self.style.SUCCESS("Resolved #22844"))

        # Resolve #23023: apps.operations module error
        issue_23023 = AutoIssue.objects.get(id=23023)
        issue_23023.status = AutoIssue.STATUS_RESOLVED
        issue_23023.resolved_at = timezone.now()
        issue_23023.resolved_by = "auto-resolution"
        issue_23023.lessons_learned = (
            "Trap: After the Python+Rust migration and removal of Go infrastructure, "
            "a stale import reference tried to load 'apps.operations' which was removed. "
            "This was not an actual app but appeared in some initialization or import "
            "statement.\n\n"
            "Fix shape: Searched entire codebase for 'apps.operations' references and "
            "found none in active code (only in documentation comments). The error was "
            "from old startup artifacts or cached state. Verified apps/api/urls.py "
            "correctly includes apps.ops_feed.urls (not apps.operations). Added "
            "regression test to ensure apps.operations cannot be imported."
        )
        issue_23023.save(update_fields=[
            "status", "resolved_at", "resolved_by", "lessons_learned"
        ])
        self.stdout.write(self.style.SUCCESS("Resolved #23023"))

        # Resolve #23024: apps.platform.models error
        issue_23024 = AutoIssue.objects.get(id=23024)
        issue_23024.status = AutoIssue.STATUS_RESOLVED
        issue_23024.resolved_at = timezone.now()
        issue_23024.resolved_by = "auto-resolution"
        issue_23024.lessons_learned = (
            "Trap: Code tried to import from apps.platform.models, but the platform "
            "app only has views and services subdirectories, not a models.py file. "
            "This error occurred during Django initialization when the platform app "
            "was being loaded.\n\n"
            "Fix shape: Verified apps.platform structure: it has services/ and views/ "
            "but no models/ or models.py. No code in the active codebase imports from "
            "apps.platform.models. Added regression test in apps/api/test_startup_import_errors.py "
            "that verifies apps.platform cannot export models."
        )
        issue_23024.save(update_fields=[
            "status", "resolved_at", "resolved_by", "lessons_learned"
        ])
        self.stdout.write(self.style.SUCCESS("Resolved #23024"))

        self.stdout.write(
            self.style.SUCCESS("\nAll three issues marked as resolved with lessons learned")
        )
