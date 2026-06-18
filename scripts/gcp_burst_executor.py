"""Fail-closed Google Cloud burst runner for mutation shards."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

_GCLOUD_IMAGE = "gcr.io/google.com/cloudsdktool/google-cloud-cli:stable"
_DEFAULT_MAX_VMS = 12
_DEFAULT_BUDGET_CAP_EUR = 20.0
_MAX_ALLOWED_VMS = 50


@dataclass(frozen=True, slots=True)
class BurstConfig:
    """Validated Google Cloud burst settings."""

    project: str
    region: str
    budget_cap_eur: float
    max_vms: int

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.project:
            errors.append("GCP project is required.")
        if not self.region:
            errors.append("GCP region is required.")
        if self.budget_cap_eur <= 0:
            errors.append("Monthly budget cap must be greater than zero.")
        if self.max_vms < 1 or self.max_vms > _MAX_ALLOWED_VMS:
            errors.append("Maximum VM count must be between 1 and 50.")
        return tuple(errors)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paid Google Cloud mutation burst.")
    parser.add_argument("--project", default="", help="Google Cloud project id.")
    parser.add_argument("--region", default="", help="Google Cloud region.")
    parser.add_argument("--max-vms", type=int, default=_DEFAULT_MAX_VMS)
    parser.add_argument("--budget-cap-eur", type=float, default=_DEFAULT_BUDGET_CAP_EUR)
    parser.add_argument("--job-name", default="xf-mutation-burst")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-paid-run", action="store_true")
    return parser.parse_args(argv)


def build_gcloud_container_command(config: BurstConfig, *, job_name: str) -> list[str]:
    """Return the containerized gcloud command without running it."""
    return [
        "docker",
        "run",
        "--rm",
        _GCLOUD_IMAGE,
        "gcloud",
        "batch",
        "jobs",
        "submit",
        job_name,
        "--project",
        config.project,
        "--location",
        config.region,
        "--labels",
        f"xf_max_vms={config.max_vms},xf_budget_cap_eur={config.budget_cap_eur:g}",
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = BurstConfig(
        project=args.project.strip(),
        region=args.region.strip(),
        budget_cap_eur=args.budget_cap_eur,
        max_vms=args.max_vms,
    )
    errors = config.validation_errors()
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 2
    command = build_gcloud_container_command(config, job_name=args.job_name)
    if args.dry_run:
        print("DRY RUN:", " ".join(command))
        return 0
    if not args.confirm_paid_run:
        print("FAIL: paid Google Cloud burst needs --confirm-paid-run.", file=sys.stderr)
        return 2
    subprocess.run(command, check=True, timeout=60 * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
