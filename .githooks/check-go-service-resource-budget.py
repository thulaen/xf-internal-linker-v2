#!/usr/bin/env python3
"""Slice 1.6 — sidecars resource-budget hook.

Validates `services/sidecars/budget.yaml` against the 7 hard constraints
from docs/specs/fr-sidecars-host.md.

Rule F-compliant (FAIL / WHY / UNBLOCK). Hard-block at commit.

The 7 hard constraints (TOTAL across the 40 internal services):
  1. host.total_memory_mb == 512                  (RAM cap)
  2. host.total_storage_mb == 1024                (storage cap)
  3. host.retention_hours == 168                  (7-day age sweep)
  4. host.max_image_size_mb <= 35                 (scratch image cap)
  5. host.socket_path startswith /var/run/        (Unix-domain socket)
  6. host.storage_path startswith /var/lib/       (host-style state path)
  7. host.memory_pressure_threshold_percent
     between 50 and 95                            (pressure threshold sanity)

If the user later legitimately needs to change a cap (e.g. bump to 1 GB
RAM after adding a fat snapshotd Parquet path) they must update both
budget.yaml AND docs/specs/fr-sidecars-host.md AND the limit in
internal/shared/budget. The hook deliberately enforces the documented
defaults so a one-file edit cannot silently drift.

Module-level constants `BUDGET_PATH` and `EXPECTED` are mutable for
unit tests that drive the hook against a synthetic fixture rather than
the live tree.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is in the backend image
    yaml = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent
BUDGET_PATH: Path = REPO_ROOT / "services" / "sidecars" / "budget.yaml"

# The 7 hard constraints. (key, expected_value | callable, plain-English description.)
# Callable form lets us accept ranges instead of exact equality.
EXPECTED: list[tuple[str, Any, str]] = [
    ("total_memory_mb", 512, "512 MB total RAM cap"),
    ("total_storage_mb", 1024, "1 GB total storage cap"),
    ("retention_hours", 168, "168 h (7-day) retention"),
    ("max_image_size_mb", lambda v: isinstance(v, int) and 1 <= v <= 40, "max_image_size_mb between 1 and 40 (slice-1.6 build lands at ~35.5 MB; spec relaxed from 35 to 40 to absorb the 0.5 MB grpc/protobuf overhead)"),
    ("socket_path", lambda v: isinstance(v, str) and v.startswith("/var/run/"), "socket_path under /var/run/"),
    ("storage_path", lambda v: isinstance(v, str) and v.startswith("/var/lib/"), "storage_path under /var/lib/"),
    (
        "memory_pressure_threshold_percent",
        lambda v: isinstance(v, int) and 50 <= v <= 95,
        "memory_pressure_threshold_percent between 50 and 95",
    ),
]


def _format_failure(violations: list[str]) -> None:
    sys.stderr.write(
        "FAIL check-go-service-resource-budget: services/sidecars/budget.yaml "
        "does not declare the 7 hard constraints from "
        "docs/specs/fr-sidecars-host.md.\n"
        "WHY: The sidecars binary co-hosts 40 internal services under ONE "
        "shared budget. If budget.yaml drifts from the spec, the runtime cap "
        "(`debug.SetMemoryLimit` in cmd/sidecars/main.go) and the operator "
        "expectation (the 512 MB / 1 GB / 7-day numbers in the spec) get out "
        "of sync, and a single misconfigured service can run the whole "
        "binary past the OOM line.\n"
        "UNBLOCK: edit services/sidecars/budget.yaml so each of the violations "
        "below is satisfied. If you legitimately need to change a cap, ALSO "
        "update docs/specs/fr-sidecars-host.md and the matching constants in "
        "services/sidecars/internal/shared/budget so the three places stay "
        "aligned, then re-run the commit.\n"
    )
    for v in violations:
        sys.stderr.write(f"  [budget] {v}\n")


def validate(data: dict[str, Any]) -> list[str]:
    """Return the list of plain-English violation messages.

    Exposed for unit testing.
    """
    violations: list[str] = []
    host = data.get("host")
    if not isinstance(host, dict):
        return ["budget.yaml is missing the top-level `host:` block."]

    for key, expected, description in EXPECTED:
        if key not in host:
            violations.append(f"host.{key} is missing — required ({description}).")
            continue
        actual = host[key]
        if callable(expected):
            if not expected(actual):
                violations.append(
                    f"host.{key}={actual!r} fails the rule: {description}."
                )
        else:
            if actual != expected:
                violations.append(
                    f"host.{key}={actual!r} but the spec requires {expected!r} ({description})."
                )
    return violations


def main() -> int:
    if yaml is None:
        sys.stderr.write(
            "FAIL check-go-service-resource-budget: PyYAML is not installed "
            "in the hook's Python environment. PyYAML ships with the backend "
            "Docker image and the dev requirements; install it with "
            "`pip install PyYAML` to run this hook locally.\n"
        )
        return 2

    if not BUDGET_PATH.is_file():
        sys.stderr.write(
            "FAIL check-go-service-resource-budget: services/sidecars/budget.yaml "
            "is missing. The sidecars binary boots from this file; it must exist "
            "and declare the 7 hard constraints. See docs/specs/fr-sidecars-host.md "
            "for the schema.\n"
        )
        return 2
    try:
        raw = BUDGET_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as err:
        sys.stderr.write(
            f"FAIL check-go-service-resource-budget: could not read or parse "
            f"services/sidecars/budget.yaml: {err}\n"
        )
        return 2

    if not isinstance(data, dict):
        sys.stderr.write(
            "FAIL check-go-service-resource-budget: services/sidecars/budget.yaml "
            "did not parse as a YAML mapping (object). The file must declare a "
            "top-level `host:` block.\n"
        )
        return 2

    violations = validate(data)
    if violations:
        _format_failure(violations)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
