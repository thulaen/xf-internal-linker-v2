"""Ad-hoc memory profiling via memray.

Closes Gap #4 from `docs/OBSERVABILITY-GAPS-EXTENSION.md` (memory leaks
that GlitchTip + Pyroscope don't catch). Run this command when backend
RAM has been creeping over a few days and you want a flamegraph of
which Python code is holding the memory.

Why on-demand and not continuous: memray as a continuous profiler
costs ~5% CPU + ~10-20% memory overhead. For a single-host dev stack
that's not worth paying every minute. Run this command WHEN you observe
high RAM, not always.

Usage:
    python scripts/backend_manage.py memray_report --duration 60
    # → /app/memray-<timestamp>.bin and /app/memray-<timestamp>.html

The HTML report opens in any browser and shows a flamegraph of every
allocation captured during the recording window.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
import time
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Record a memray flamegraph of THIS Django process for N seconds."

    _DEFAULT_DURATION_S = 60
    _DEFAULT_OUTPUT_DIR = Path("/app")

    def add_arguments(self, parser):
        parser.add_argument(
            "--duration",
            type=int,
            default=self._DEFAULT_DURATION_S,
            help=f"Recording window in seconds (default {self._DEFAULT_DURATION_S}).",
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=self._DEFAULT_OUTPUT_DIR,
            help="Where to write the .bin and .html files. Mounted at /app by default.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show where the report would be written without recording memory.",
        )

    def handle(self, *args, **opts):
        duration = opts["duration"]
        output_dir: Path = opts["output_dir"]
        if opts["dry_run"]:
            self._write_dry_run(duration, output_dir)
            return

        memray_module = self._load_memray()
        if memray_module is None:
            self.stderr.write(
                "memray not installed. Add `memray` to requirements.txt + rebuild."
            )
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        bin_path = output_dir / f"memray-{timestamp}.bin"
        html_path = output_dir / f"memray-{timestamp}.html"

        self.stdout.write(
            f"Recording memory allocations for {duration}s → {bin_path}"
        )
        with memray_module.Tracker(str(bin_path), native_traces=True):
            # Sit and let other Python work happen elsewhere in the
            # process (Celery tasks running in this same process via
            # `manage.py shell` etc.). For a Celery-worker process,
            # invoke `manage.py memray_report` separately and let the
            # worker keep doing its thing in parallel.
            time.sleep(duration)

        self.stdout.write(f"Recording done. Generating flamegraph → {html_path}")
        self._write_flamegraph(bin_path, html_path)

    def _write_dry_run(self, duration: int, output_dir: Path) -> None:
        self.stdout.write(
            f"Dry run only. Would record for {duration}s and write under {output_dir}."
        )

    def _load_memray(self):
        try:
            import memray
        except ImportError:
            return None
        return memray

    def _write_flamegraph(self, bin_path: Path, html_path: Path) -> None:
        # subprocess.run with a list arg (no shell=True) avoids shell-injection
        # via filesystem paths that may contain unusual characters. Bandit
        # B605 specifically asks for this pattern.
        memray_bin = shutil.which("memray")
        if not memray_bin:
            self.stderr.write("memray executable not found on PATH.")
            return
        completed = subprocess.run(
            [memray_bin, "flamegraph", str(bin_path), "-o", str(html_path)],
            check=False,
        )  # nosec B603
        if completed.returncode != 0:
            self.stderr.write(
                "memray flamegraph subcommand failed. The .bin file is "
                f"still at {bin_path} — run `memray flamegraph {bin_path}` "
                f"manually."
            )
            return
        self.stdout.write(self.style.SUCCESS(f"Flamegraph: {html_path}"))
