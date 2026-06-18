"""Start an embedding-provider score run from the command line."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.tasks_embedding_bakeoff import embedding_provider_bakeoff


class Command(BaseCommand):
    help = "Start a cost-confirmed embedding provider score run."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--sample-size", type=int, default=1000)
        parser.add_argument("--confirm-cost", action="store_true")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the provider score run that would start without charging providers.",
        )

    def handle(self, *args, **options) -> str:
        sample_size = max(1, min(int(options["sample_size"]), 200_000))
        if options["dry_run"]:
            message = (
                "Dry run only. Would start a provider score run with "
                f"sample size {sample_size}; no task was queued."
            )
            self.stdout.write(message)
            return message
        if not options["confirm_cost"]:
            raise CommandError("--confirm-cost is required because providers may charge per call.")
        result = embedding_provider_bakeoff.delay(sample_size=sample_size)
        message = f"Started provider score run task {result.id} with sample size {sample_size}."
        self.stdout.write(message)
        return message
