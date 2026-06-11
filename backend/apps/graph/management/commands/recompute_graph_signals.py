from django.core.management.base import BaseCommand
from apps.graph.services.graph_signal_job import run_signals

class Command(BaseCommand):
    help = "Recomputes graph signals and saves them to the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run all computations but roll back the database transaction at the end.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force computation even if the graph hash hasn't changed.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]

        self.stdout.write(f"Starting graph signal computation (dry_run={dry_run}, force={force})...")
        run, result = run_signals(force=force, dry_run=dry_run)
        
        if result is None:
            self.stdout.write(self.style.SUCCESS("Graph unchanged. Skipped computation."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully computed signals for {run.node_count} nodes and {run.edge_count} edges."))
