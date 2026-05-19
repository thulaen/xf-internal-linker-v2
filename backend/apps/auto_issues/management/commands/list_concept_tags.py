"""Print the approved AutoIssue concept-tag vocabulary."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.auto_issues.concept_tags import ALLOWED_CONCEPT_TAGS


class Command(BaseCommand):
    help = "Print approved AutoIssue concept tags, one per line."

    def handle(self, *args, **options) -> None:
        for tag in sorted(ALLOWED_CONCEPT_TAGS):
            self.stdout.write(tag)
