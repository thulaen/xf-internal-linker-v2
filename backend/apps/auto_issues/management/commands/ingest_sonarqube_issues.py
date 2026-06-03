"""Import SonarQube findings into AutoIssues."""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand

from apps.auto_issues.services.sonarqube import (
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    SonarQubeUnavailable,
    fetch_sonar_issues,
    ingest_sonarqube_issues,
)


class Command(BaseCommand):
    help = "Fetch unresolved SonarQube findings and file them as AutoIssues."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--base-url", default=os.getenv("SONAR_HOST_URL", "http://sonarqube:9000"))
        parser.add_argument("--project-key", default=os.getenv("SONAR_PROJECT_KEY", "xf-internal-linker-v2"))
        parser.add_argument("--token", default=os.getenv("SONAR_TOKEN", ""))
        parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
        parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)

    def handle(self, *args, **options) -> None:
        try:
            issues = fetch_sonar_issues(
                base_url=options["base_url"],
                project_key=options["project_key"],
                token=options["token"],
                page_size=options["page_size"],
                max_pages=options["max_pages"],
            )
        except SonarQubeUnavailable as exc:
            self.stdout.write(f"SONARQUBE UNAVAILABLE: {exc}")
            return
        result = ingest_sonarqube_issues(
            options["project_key"],
            issues,
            base_url=options["base_url"],
        )
        self.stdout.write(
            "SONARQUBE AUTOISSUES IMPORTED: "
            f"{result.total} total, {result.created} created, "
            f"{result.updated} updated, {result.merged} merged"
        )
