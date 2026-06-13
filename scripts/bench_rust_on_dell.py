#!/usr/bin/env python3
"""Run the Rust kernels' Criterion benchmarks on Dell and record the results.

This is the host-side half of the Rust benchmark pipeline (the backend
container cannot reach Dell's Docker, so the cargo run happens here). For each
kernel crate it runs ``cargo bench -p <kernel> -- --output-format bencher`` via
``scripts/dell-rust.sh`` (which syncs the workspace to Dell and runs cargo in
the compiled-tools image), parses Criterion's bencher-format nanosecond lines,
and writes a JSON list. With ``--record`` it then feeds that JSON into the
backend via ``manage.py record_rust_benchmarks`` so the performance-regression
gate has Rust history to read.

Usage:
  python scripts/bench_rust_on_dell.py --kernels scoring texttok --record
  python scripts/bench_rust_on_dell.py --all --out /tmp/rust_bench.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404 — fixed argv, no shell, no user input
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Criterion's `--output-format bencher` prints, per benchmark id:
#   test <group>/<value> ... bench:        1234 ns/iter (+/- 56)
_BENCHER_RE = re.compile(
    r"^test\s+(?P<name>\S+)\s+\.\.\.\s+bench:\s+(?P<ns>[\d,]+)\s+ns/iter"
)


def parse_bencher_output(text: str, extension: str) -> list[dict]:
    """Parse bencher-format lines into BenchmarkResult-shaped dicts.

    Pure function (no IO) so it unit-tests without a cargo run. The Criterion
    benchmark id ``<group>/<value>`` maps to function_name + input_size; an id
    with no ``/`` uses input_size ``default``.
    """
    rows: list[dict] = []
    for line in text.splitlines():
        m = _BENCHER_RE.match(line.strip())
        if not m:
            continue
        name = m.group("name")
        mean_ns = int(m.group("ns").replace(",", ""))
        if "/" in name:
            function_name, input_size = name.rsplit("/", 1)
        else:
            function_name, input_size = name, "default"
        rows.append({
            "extension": extension,
            "function_name": function_name,
            "input_size": input_size,
            "mean_ns": mean_ns,
            "median_ns": mean_ns,  # bencher format reports a single point estimate
        })
    return rows


def _kernels_from_workspace() -> list[str]:
    members = (ROOT / "rust" / "Cargo.toml").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'extensions/([A-Za-z0-9_]+)"', members)))


def _run_bench(kernel: str, bash: str) -> str:
    cmd = [bash, str(ROOT / "scripts" / "dell-rust.sh"),
           "bench", "-p", kernel, "--", "--output-format", "bencher"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))  # nosec B603
    if proc.returncode != 0:
        sys.stderr.write(f"[bench-rust] {kernel}: cargo bench failed\n{proc.stderr[-2000:]}\n")
    return proc.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Rust Criterion benches on Dell.")
    ap.add_argument("--kernels", nargs="*", help="Kernel crate names (default: --all).")
    ap.add_argument("--all", action="store_true", help="Bench every kernel crate.")
    ap.add_argument("--out", default=str(ROOT / ".tmp" / "rust_bench.json"))
    ap.add_argument("--record", action="store_true",
                    help="Feed results into the backend via record_rust_benchmarks.")
    ap.add_argument("--bash", default="/c/Program Files/Git/bin/bash.exe",
                    help="bash used to invoke dell-rust.sh (Git-Bash on Windows).")
    args = ap.parse_args()

    kernels = args.kernels or (_kernels_from_workspace() if args.all else [])
    if not kernels:
        ap.error("pass --kernels <names> or --all")

    results: list[dict] = []
    for kernel in kernels:
        results.extend(parse_bencher_output(_run_bench(kernel, args.bash), kernel))
    if not results:
        sys.stderr.write("[bench-rust] no benchmark results parsed; aborting.\n")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"[bench-rust] wrote {len(results)} result(s) to {out_path}")

    if args.record:
        rc = subprocess.run(  # nosec B603 B607 — fixed argv
            ["docker", "compose", "exec", "-T", "backend", "python", "manage.py",
             "record_rust_benchmarks", "--json", f"/app/{out_path.name}"],
            cwd=str(ROOT),
        ).returncode
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
