"""Fail-closed spend guard for optional Google Cloud mutation bursts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass

_TABLE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+[.][A-Za-z0-9_]+[.][A-Za-z0-9_]+$")
_DEFAULT_REFUSE_AT_EUR = 18.0


@dataclass(frozen=True, slots=True)
class SpendGuardConfig:
    """Settings needed to query month-to-date Google Cloud spend."""

    billing_project: str
    billing_export_table: str
    gcp_project: str
    refuse_at_eur: float = _DEFAULT_REFUSE_AT_EUR

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.billing_project:
            errors.append("Billing project is required for the spend guard.")
        if not self.billing_export_table:
            errors.append("Billing export table is required for the spend guard.")
        elif not _TABLE_ID_RE.fullmatch(self.billing_export_table):
            errors.append("Billing export table must be project.dataset.table.")
        if not self.gcp_project:
            errors.append("Google Cloud project is required for the spend guard.")
        if self.refuse_at_eur <= 0:
            errors.append("Spend refusal limit must be greater than zero.")
        return tuple(errors)


@dataclass(frozen=True, slots=True)
class SpendGuardResult:
    """Decision returned by the Google Cloud spend guard."""

    allowed: bool
    status: str
    month_to_date_eur: float | None
    refuse_at_eur: float
    message: str

    @classmethod
    def fail_closed(
        cls,
        message: str,
        refuse_at_eur: float = _DEFAULT_REFUSE_AT_EUR,
    ) -> SpendGuardResult:
        return cls(
            allowed=False,
            status="unavailable",
            month_to_date_eur=None,
            refuse_at_eur=refuse_at_eur,
            message=message,
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> SpendGuardResult:
        allowed = payload.get("allowed")
        if not isinstance(allowed, bool):
            return cls.fail_closed("Spend proof allowed flag was invalid.")
        try:
            month_to_date_eur = _optional_float(payload.get("month_to_date_eur"))
            refuse_at_eur = float(payload.get("refuse_at_eur", _DEFAULT_REFUSE_AT_EUR))
        except (TypeError, ValueError) as exc:
            return cls.fail_closed(f"Spend proof numeric field was invalid: {exc}")
        return cls(
            allowed=allowed,
            status=str(payload.get("status", "unavailable")),
            month_to_date_eur=month_to_date_eur,
            refuse_at_eur=refuse_at_eur,
            message=str(payload.get("message", "Spend proof loaded.")),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "month_to_date_eur": self.month_to_date_eur,
            "refuse_at_eur": self.refuse_at_eur,
            "message": self.message,
        }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def build_month_to_date_query(config: SpendGuardConfig) -> str:
    """Build the BigQuery billing-export query used by the spend guard."""
    table = config.billing_export_table
    project = config.gcp_project.replace("'", "\\'")
    return "\n".join(
        [
            "SELECT COALESCE(SUM(cost), 0) AS month_to_date_eur",
            f"FROM `{table}`",
            f"WHERE project.id = '{project}'",
            "  AND invoice.month = FORMAT_DATE('%Y%m', CURRENT_DATE())",
        ]
    )


def build_bq_command(config: SpendGuardConfig) -> list[str]:
    """Return the billing query command without running it."""
    return [
        "bq",
        "--project_id",
        config.billing_project,
        "query",
        "--use_legacy_sql=false",
        "--format=json",
        build_month_to_date_query(config),
    ]


def check_spend_guard(
    config: SpendGuardConfig,
    *,
    runner=subprocess.run,
) -> SpendGuardResult:
    """Return a fail-closed spend decision from the billing export."""
    errors = config.validation_errors()
    if errors:
        return SpendGuardResult.fail_closed(" ".join(errors), config.refuse_at_eur)
    try:
        completed = runner(
            build_bq_command(config),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return SpendGuardResult.fail_closed(f"Spend check failed: {exc}", config.refuse_at_eur)
    return evaluate_billing_rows(completed.stdout, refuse_at_eur=config.refuse_at_eur)


def evaluate_billing_rows(raw_json: str, *, refuse_at_eur: float) -> SpendGuardResult:
    """Evaluate BigQuery JSON rows and refuse when spend is too high."""
    try:
        rows = json.loads(raw_json)
        spend = float(rows[0]["month_to_date_eur"]) if rows else 0.0
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return SpendGuardResult.fail_closed(f"Spend check output was invalid: {exc}", refuse_at_eur)
    if spend >= refuse_at_eur:
        return SpendGuardResult(
            allowed=False,
            status="refused",
            month_to_date_eur=spend,
            refuse_at_eur=refuse_at_eur,
            message=f"Month-to-date spend is {spend:.2f} EUR, at or above {refuse_at_eur:.2f} EUR.",
        )
    return SpendGuardResult(
        allowed=True,
        status="ok",
        month_to_date_eur=spend,
        refuse_at_eur=refuse_at_eur,
        message=f"Month-to-date spend is {spend:.2f} EUR, below {refuse_at_eur:.2f} EUR.",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Google Cloud month-to-date spend.")
    parser.add_argument("--billing-project", default="")
    parser.add_argument("--billing-export-table", default="")
    parser.add_argument("--gcp-project", default="")
    parser.add_argument("--refuse-at-eur", type=float, default=_DEFAULT_REFUSE_AT_EUR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = SpendGuardConfig(
        billing_project=args.billing_project.strip(),
        billing_export_table=args.billing_export_table.strip(),
        gcp_project=args.gcp_project.strip(),
        refuse_at_eur=args.refuse_at_eur,
    )
    if args.dry_run:
        print(json.dumps({"command": build_bq_command(config)}, indent=2))
        return 0
    result = check_spend_guard(config)
    print(json.dumps(result.to_mapping(), indent=2, sort_keys=True))
    return 0 if result.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
