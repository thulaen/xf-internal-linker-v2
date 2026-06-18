"""Fail-closed Google Cloud burst planner for mutation shards."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from gcp_spend_guard import SpendGuardConfig, SpendGuardResult, check_spend_guard

_DEFAULT_MAX_VMS = 12
_DEFAULT_BUDGET_CAP_EUR = 20.0
_DEFAULT_REFUSE_AT_EUR = 18.0
_DEFAULT_MAX_VM_MINUTES = 20
_MAX_ALLOWED_VMS = 50
_DEFAULT_MACHINE_TYPE = "c3-highcpu-8"
_RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class BurstConfig:
    """Validated Google Cloud burst settings."""

    project: str
    region: str
    budget_cap_eur: float
    max_vms: int
    refuse_at_eur: float
    max_vm_minutes: int
    machine_type: str

    @property
    def planned_vms(self) -> int:
        return min(self.max_vms, _DEFAULT_MAX_VMS)

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
        if self.refuse_at_eur <= 0 or self.refuse_at_eur > self.budget_cap_eur:
            errors.append("Spend refusal limit must be greater than zero and at or below the budget cap.")
        if self.max_vm_minutes < 1:
            errors.append("Maximum VM minutes must be greater than zero.")
        if not self.machine_type:
            errors.append("Google Cloud machine type is required.")
        return tuple(errors)


@dataclass(frozen=True, slots=True)
class BurstPlan:
    """No-spend plan record for the optional Google Cloud mutation burst."""

    config: BurstConfig
    job_name: str
    full: bool
    spend: SpendGuardResult

    def to_record(self) -> dict[str, object]:
        command = build_gcloud_batch_command(self.config, job_name=self.job_name)
        return {
            "schema_version": _RESULT_SCHEMA_VERSION,
            "job_name": self.job_name,
            "mode": "full" if self.full else "diff",
            "planned-vms": self.config.planned_vms,
            "requested-vms": self.config.max_vms,
            "max-vm-minutes": self.config.max_vm_minutes,
            "machine-type": self.config.machine_type,
            "estimated-max-eur": estimate_max_cost_eur(self.config),
            "budget-cap-eur": self.config.budget_cap_eur,
            "spend-refuse-at-eur": self.config.refuse_at_eur,
            "spend-check-status": self.spend.status,
            "spend-check-message": self.spend.message,
            "paid-run-required": True,
            "would-submit": self.spend.allowed,
            "gcloud-command": command,
            "result-record": build_result_record(self.config, self.job_name, self.spend),
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paid Google Cloud mutation burst.")
    parser.add_argument("--project", default="", help="Google Cloud project id.")
    parser.add_argument("--region", default="", help="Google Cloud region.")
    parser.add_argument("--max-vms", type=int, default=_DEFAULT_MAX_VMS)
    parser.add_argument("--budget-cap-eur", type=float, default=_DEFAULT_BUDGET_CAP_EUR)
    parser.add_argument("--refuse-at-eur", type=float, default=_DEFAULT_REFUSE_AT_EUR)
    parser.add_argument("--max-vm-minutes", type=int, default=_DEFAULT_MAX_VM_MINUTES)
    parser.add_argument("--machine-type", default=_DEFAULT_MACHINE_TYPE)
    parser.add_argument("--job-name", default="xf-mutation-burst")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-paid-run", action="store_true")
    parser.add_argument("--billing-project", default="")
    parser.add_argument("--billing-export-table", default="")
    parser.add_argument("--spend-json", default="")
    return parser.parse_args(argv)


def estimate_max_cost_eur(config: BurstConfig) -> float:
    """Return the safe upper cost shown to the operator before any paid run."""
    return round(min(config.budget_cap_eur, config.refuse_at_eur), 2)


def build_gcloud_batch_command(config: BurstConfig, *, job_name: str) -> list[str]:
    """Return the Google Cloud Batch command without running it."""
    return [
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
        f"xf_max_vms={config.planned_vms},xf_budget_cap_eur={config.budget_cap_eur:g}",
        "--config",
        "infra/gcp/budget-autodisable/batch-job-template.json",
    ]


def build_result_record(config: BurstConfig, job_name: str, spend: SpendGuardResult) -> dict[str, object]:
    """Return the merge-compatible burst status record."""
    return {
        "schema_version": _RESULT_SCHEMA_VERSION,
        "source": "gcp-spot",
        "job_name": job_name,
        "status": "planned" if spend.allowed else "local_only",
        "retryable": not spend.allowed,
        "planned_vms": config.planned_vms,
        "estimated_max_eur": estimate_max_cost_eur(config),
        "spend_status": spend.status,
        "message": spend.message,
    }


def build_plan(args: argparse.Namespace, spend: SpendGuardResult | None = None) -> BurstPlan:
    config = BurstConfig(
        project=args.project.strip(),
        region=args.region.strip(),
        budget_cap_eur=args.budget_cap_eur,
        max_vms=args.max_vms,
        refuse_at_eur=args.refuse_at_eur,
        max_vm_minutes=args.max_vm_minutes,
        machine_type=args.machine_type.strip(),
    )
    spend_result = spend or _read_or_check_spend(args, config)
    return BurstPlan(
        config=config,
        job_name=args.job_name.strip() or "xf-mutation-burst",
        full=args.full,
        spend=spend_result,
    )


def _read_or_check_spend(args: argparse.Namespace, config: BurstConfig) -> SpendGuardResult:
    if args.spend_json:
        return _load_spend_result(Path(args.spend_json))
    guard_config = SpendGuardConfig(
        billing_project=args.billing_project.strip(),
        billing_export_table=args.billing_export_table.strip(),
        gcp_project=config.project,
        refuse_at_eur=config.refuse_at_eur,
    )
    return check_spend_guard(guard_config)


def _load_spend_result(path: Path) -> SpendGuardResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return SpendGuardResult.fail_closed(f"Spend proof could not be read: {exc}")
    return SpendGuardResult.from_mapping(payload)


def _print_json(record: dict[str, object]) -> None:
    print(json.dumps(record, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_plan(args)
    errors = plan.config.validation_errors()
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 2
    if args.dry_run:
        _print_json(plan.to_record())
        return 0
    if not args.confirm_paid_run:
        print("FAIL: paid Google Cloud burst needs --confirm-paid-run.", file=sys.stderr)
        return 2
    if not plan.spend.allowed:
        print(f"FAIL: {plan.spend.message}", file=sys.stderr)
        return 2
    subprocess.run(
        build_gcloud_batch_command(plan.config, job_name=plan.job_name),
        check=True,
        timeout=plan.config.max_vm_minutes * 60,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
