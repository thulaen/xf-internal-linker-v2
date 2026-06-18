#!/usr/bin/env python3
"""Dry-run coordinator for Kubernetes distributed quality runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gcp_spend_guard import SpendGuardResult

PREFLIGHT_CHECKS: tuple[str, ...] = (
    "cluster-api-ready",
    "dell-node-ready",
    "mint-storage-ready",
    "registry-mirror-ready",
    "runner-images-pinned",
    "source-snapshot-uploaded",
    "bazel-remote-cache-ready",
    "buildbuddy-app-ready",
    "postgres-service-ready",
    "frontend-http-ready",
    "worker-queue-ready",
    "msi-docker-free",
)

_DEFAULT_GCP_MAX_VMS = 12
_DEFAULT_GCP_BUDGET_CAP_EUR = 20.0
_DEFAULT_GCP_REFUSE_AT_EUR = 18.0
_GCP_DRY_RUN_SPEND = SpendGuardResult(
    allowed=True,
    status="dry-run",
    month_to_date_eur=None,
    refuse_at_eur=_DEFAULT_GCP_REFUSE_AT_EUR,
    message="Dry-run planning only; no paid Google Cloud work will start.",
)

DELL_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "pytest",
        "ruff",
        "mypy",
        "mutmut",
        "cargo-nextest",
        "cargo-mutants",
        "vitest",
        "eslint",
        "stryker",
    }
)


def _default_shards() -> list[dict[str, str]]:
    return [
        {"id": "python-tests", "tool": "pytest", "command": "toolbox pytest"},
        {"id": "python-lint", "tool": "ruff", "command": "toolbox ruff"},
        {"id": "rust-tests", "tool": "cargo-nextest", "command": "cargo nextest run"},
        {"id": "frontend-tests", "tool": "vitest", "command": "toolbox vitest"},
    ]


def _mutation_shards(full: bool) -> list[dict[str, str]]:
    scope = "full" if full else "diff"
    return [
        {
            "id": f"python-mutation-{scope}",
            "tool": "mutmut",
            "command": f"tools/quality/internal/run-python-mutation.sh --{scope}",
        },
        {
            "id": f"rust-mutation-{scope}",
            "tool": "cargo-mutants",
            "command": f"tools/quality/internal/run-rust-mutation.sh --{scope}",
        },
        {
            "id": f"frontend-mutation-{scope}",
            "tool": "stryker",
            "command": f"tools/quality/internal/run-angular-mutation.sh --{scope}",
        },
    ]


def _placement_for(tool: str) -> str:
    if tool in DELL_ONLY_TOOLS:
        return "dell"
    return "dell"


def build_plan(
    run_id: str,
    timeout_minutes: int,
    *,
    burst: str = "none",
    full: bool = False,
    spend: SpendGuardResult | None = None,
) -> dict:
    """Build the dry-run plan used by shell and PowerShell launchers."""
    shards = []
    for shard in _default_shards():
        shards.append({**shard, "placement": _placement_for(shard["tool"])})
    burst_plan = _build_burst_plan(run_id, burst=burst, full=full, spend=spend)
    shards.extend(burst_plan["shards"])
    return {
        "run_id": run_id,
        "mode": "dry-run",
        "timeout_minutes": timeout_minutes,
        "preflight_checks": list(PREFLIGHT_CHECKS),
        "shards": shards,
        "merge": {"id": "merge-report", "placement": "dell"},
        "burst": burst_plan["summary"],
    }


def _build_burst_plan(
    run_id: str,
    *,
    burst: str,
    full: bool,
    spend: SpendGuardResult | None,
) -> dict[str, object]:
    if burst == "none":
        return {"summary": {"provider": "none", "status": "local-only"}, "shards": []}
    if burst != "gcp":
        return {"summary": {"provider": burst, "status": "unsupported"}, "shards": []}
    spend = spend or SpendGuardResult.fail_closed("Spend guard was not configured.")
    if not spend.allowed:
        return {
            "summary": {
                "provider": "gcp",
                "status": "local-only",
                "spend-check-status": spend.status,
                "message": spend.message,
            },
            "shards": [],
        }
    shards = []
    for shard in _mutation_shards(full):
        shards.append({**shard, "placement": "gcp-spot", "run_id": run_id})
    return {
        "summary": {
            "provider": "gcp",
            "status": "planned",
            "planned-vms": min(len(shards), _DEFAULT_GCP_MAX_VMS),
            "budget-cap-eur": _DEFAULT_GCP_BUDGET_CAP_EUR,
            "spend-refuse-at-eur": _DEFAULT_GCP_REFUSE_AT_EUR,
            "spend-check-status": spend.status,
        },
        "shards": shards,
    }


def _render_shard_job(run_id: str, shard: dict[str, str], timeout_minutes: int) -> str:
    node_selector = (
        'xf.io/can-test: "true"'
        if shard["placement"] == "dell"
        else 'xf.io/cloud-burst: "gcp"'
    )
    return "\n".join(
        [
            "apiVersion: batch/v1",
            "kind: Job",
            "metadata:",
            f"  name: xf-{run_id}-{shard['id']}",
            "  namespace: xf-build",
            "spec:",
            f"  activeDeadlineSeconds: {timeout_minutes * 60}",
            "  template:",
            "    spec:",
            "      nodeSelector:",
            f"        {node_selector}",
            "      restartPolicy: Never",
            "      containers:",
            "        - name: shard",
            "          image: 10.10.10.91:5000/xf-runner-python@sha256:"
            "9838f284407976418a52a13239a96f01545d9817cb3e562a45630310cafa4654",
            f"          command: [\"/bin/sh\", \"-lc\", \"{shard['command']}\"]",
        ]
    )


def render_shard_jobs(plan: dict) -> str:
    """Render all shard jobs as one Kubernetes multi-document YAML string."""
    jobs = [
        _render_shard_job(plan["run_id"], shard, plan["timeout_minutes"])
        for shard in plan["shards"]
    ]
    return "\n---\n".join(jobs) + "\n"


def render_merge_job(plan: dict) -> str:
    """Render the merge job that validates all required shard outputs."""
    run_id = plan["run_id"]
    return "\n".join(
        [
            "apiVersion: batch/v1",
            "kind: Job",
            "metadata:",
            f"  name: xf-{run_id}-merge-report",
            "  namespace: xf-build",
            "spec:",
            f"  activeDeadlineSeconds: {plan['timeout_minutes'] * 60}",
            "  template:",
            "    spec:",
            "      nodeSelector:",
            "        xf.io/can-test: \"true\"",
            "      restartPolicy: Never",
            "      containers:",
            "        - name: merge",
            "          image: 10.10.10.91:5000/xf-runner-merge@sha256:"
            "51f0f01277b6978014ab871ea88f8d8be6e6834aaaebceb290264a8752fb5b00",
            '          command: ["/bin/sh", "-lc", '
            f'"python scripts/merge_shard_outputs.py {run_id}"]',
        ]
    ) + "\n"


def render_final_report(plan: dict, failures: list[str] | None = None) -> str:
    """Render a plain-English report for dry-run proof and failed shard runs."""
    failures = failures or []
    status = "failed" if failures else "ready"
    lines = [
        f"# Distributed quality run {plan['run_id']}",
        "",
        f"Status: {status}",
        f"Timeout: {plan['timeout_minutes']} minutes per job",
        f"Preflight checks: {len(plan['preflight_checks'])}",
        f"Shard jobs: {len(plan['shards'])}",
        f"Burst: {plan['burst']['status']}",
        "",
        "## Placement",
    ]
    lines.extend(f"- {shard['id']}: {shard['placement']}" for shard in plan["shards"])
    if failures:
        lines.append("")
        lines.append("## Failures")
        lines.extend(f"- {failure}" for failure in failures)
    return "\n".join(lines) + "\n"


def write_outputs(plan: dict, outdir: Path) -> None:
    """Write coordinator proof files to the requested output directory."""
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    (outdir / "shard-jobs.yaml").write_text(render_shard_jobs(plan), encoding="utf-8")
    (outdir / "merge-job.yaml").write_text(render_merge_job(plan), encoding="utf-8")
    (outdir / "final-report.md").write_text(render_final_report(plan), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a distributed quality dry-run plan.")
    parser.add_argument("--run-id", default="dry-run")
    parser.add_argument("--timeout-minutes", type=int, default=45)
    parser.add_argument("--outdir", default="tmp/distributed-quality")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--burst", choices=("none", "gcp"), default="none")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)

    if not args.dry_run:
        print("Refusing to create Kubernetes jobs without --dry-run.")
        return 2
    spend = _GCP_DRY_RUN_SPEND if args.burst == "gcp" else None
    plan = build_plan(
        args.run_id,
        args.timeout_minutes,
        burst=args.burst,
        full=args.full,
        spend=spend,
    )
    write_outputs(plan, Path(args.outdir))
    print(render_final_report(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
