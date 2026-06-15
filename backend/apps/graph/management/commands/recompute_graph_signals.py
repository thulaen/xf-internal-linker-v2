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
        parser.add_argument(
            "--icpc-min-community-size",
            type=int,
            default=10,
            help="Minimum Louvain community size used when computing ICPC local in-degree.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        icpc_min_community_size = options["icpc_min_community_size"]

        self.stdout.write(
            "Starting graph signal computation "
            f"(dry_run={dry_run}, force={force}, "
            f"icpc_min_community_size={icpc_min_community_size})..."
        )
        run, result = run_signals(
            force=force,
            dry_run=dry_run,
            icpc_min_community_size=icpc_min_community_size,
        )
        
        if result is None:
            self.stdout.write(self.style.SUCCESS("Graph unchanged. Skipped computation."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully computed signals for {run.node_count} nodes and {run.edge_count} edges."))
