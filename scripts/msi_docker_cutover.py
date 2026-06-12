"""Plan and verify the guarded MSI Docker removal cutover."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple


class Classification(NamedTuple):
    name: str
    action: str
    destination: str
    reason: str


class ProofRequirement(NamedTuple):
    section: str
    field: str
    label: str


MUST_COPY_VOLUMES = {
    "pgdata": ("dell-postgres", "PostgreSQL data must move by dump, restore, and count checks."),
    "media_files": ("cluster-media-storage", "User media must be copied and checksum-verified."),
    "grafana_data": ("cluster-observability-storage", "Grafana history must remain readable."),
    "loki_data": ("cluster-observability-storage", "Log history must remain readable."),
    "tempo_data": ("cluster-observability-storage", "Trace history must remain readable."),
    "alloy_data": ("cluster-observability-storage", "Collector history must remain readable."),
    "pyroscope_data": ("cluster-observability-storage", "Profile history must remain readable."),
}

DISCARD_VOLUME_SUFFIXES = {
    "frontend_dist",
    "frontend_dev_node_modules",
    "frontend_tool_cache",
    "compiled_tool_cache",
    "go_tool_mod_cache",
    "hf_cache",
    "staticfiles",
    "nginx_logs",
    "sonar_scanner_cache",
}

RECREATE_AFTER_DRAIN_SUFFIXES = {
    "redis-data",
    "redis_data",
}

REBUILD_IMAGE_PREFIXES = (
    "xf-linker-",
    "xf-internal-linker-v2-",
)

PULL_IMAGE_PREFIXES = (
    "alpine",
    "docker.io/",
    "grafana/",
    "glitchtip/",
    "nginx",
    "node",
    "otel/",
    "postgres",
    "prom/",
    "prometheuscommunity/",
    "python",
    "redis",
    "sonarqube",
    "temporalio/",
    "timberio/",
    "vectordotdev/",
)

PULL_IMAGE_NAMES = {
    "grafana/grafana",
    "grafana/loki",
    "grafana/tempo",
    "grafana/alloy",
    "pgvector/pgvector",
    "prometheuscommunity/postgres-exporter",
}

PROOF_REQUIREMENTS = (
    ProofRequirement("database", "verified", "database verified"),
    ProofRequirement("media", "verified", "media verified"),
    ProofRequirement("observability", "verified", "observability verified"),
    ProofRequirement("glitchtip", "verified", "GlitchTip verified"),
    ProofRequirement("remote_checks", "verified", "remote checks verified"),
    ProofRequirement("rollback", "verified", "rollback data present"),
    ProofRequirement("manual_review", "complete", "manual review complete"),
)


def classify_volumes(names: list[str]) -> list[Classification]:
    """Classify MSI Docker volumes before any removal is allowed."""
    return [_classify_volume(name) for name in names]


def classify_images(names: list[str]) -> list[Classification]:
    """Classify MSI Docker images before any removal is allowed."""
    return [_classify_image(name) for name in names]


def readiness_from_file(path: Path) -> tuple[bool, list[str]]:
    """Return whether the proof file allows the final MSI Docker removal step."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    missing = missing_proof_labels(payload)
    return not missing, missing


def missing_proof_labels(payload: dict[str, Any]) -> list[str]:
    """List proof labels that are still missing or false."""
    missing: list[str] = []
    for requirement in PROOF_REQUIREMENTS:
        section = payload.get(requirement.section, {})
        if not isinstance(section, dict) or section.get(requirement.field) is not True:
            missing.append(requirement.label)
    return missing


def inventory_manifest(volumes: list[str], images: list[str]) -> dict[str, Any]:
    """Build a reviewable cutover manifest from raw Docker names."""
    volume_rows = classify_volumes(volumes)
    image_rows = classify_images(images)
    return {
        "volumes": [_as_dict(row) for row in volume_rows],
        "images": [_as_dict(row) for row in image_rows],
        "summary": {
            "volume_actions": _count_actions(volume_rows),
            "image_actions": _count_actions(image_rows),
            "destructive_step": "blocked until proof file passes",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard MSI Docker removal cutover.")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify-proof")
    verify.add_argument("--proof-file", required=True)

    classify = sub.add_parser("classify")
    classify.add_argument("--volumes-file", required=True)
    classify.add_argument("--images-file", required=True)
    classify.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.command == "verify-proof":
        return _verify_proof_command(Path(args.proof_file))

    volumes = _read_names(Path(args.volumes_file))
    images = _read_names(Path(args.images_file))
    manifest = inventory_manifest(volumes, images)
    Path(args.out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"[MSI DOCKER INVENTORY: wrote={args.out}]")
    return 0


def _verify_proof_command(path: Path) -> int:
    try:
        ready, missing = readiness_from_file(path)
    except (OSError, json.JSONDecodeError) as exc:
        print("[MSI DOCKER CUTOVER: ready=false]")
        print(f"Proof file could not be read as JSON: {exc}")
        return 2
    if ready:
        print("[MSI DOCKER CUTOVER: ready=true]")
        return 0
    print("[MSI DOCKER CUTOVER: ready=false]")
    print("Missing proof: " + ", ".join(missing))
    return 2


def _classify_volume(name: str) -> Classification:
    clean = name.strip()
    suffix = _known_suffix(clean, MUST_COPY_VOLUMES)
    if suffix:
        destination, reason = MUST_COPY_VOLUMES[suffix]
        return Classification(clean, "must-copy", destination, reason)
    if _known_suffix(clean, DISCARD_VOLUME_SUFFIXES):
        return Classification(clean, "discard", "none", "Disposable cache or build output.")
    if _known_suffix(clean, RECREATE_AFTER_DRAIN_SUFFIXES):
        return Classification(clean, "recreate-after-drain", "dell-or-cluster", "Runtime queue data must be drained first.")
    return Classification(clean, "manual-review", "operator-review", "Unknown volume; prove it is disposable before removal.")


def _classify_image(name: str) -> Classification:
    clean = name.strip()
    repository = _repository(clean)
    if clean in {"<none>:<none>", "<none>"} or repository == "<none>":
        return Classification(clean, "discard", "none", "Dangling local image with no registry name.")
    if repository.startswith(REBUILD_IMAGE_PREFIXES):
        return Classification(clean, "rebuild-on-dell-or-mint", "dell-or-mint", "Project image should be rebuilt from source.")
    if repository in PULL_IMAGE_NAMES or repository.startswith(PULL_IMAGE_PREFIXES):
        return Classification(clean, "pull-by-digest", "dell-or-mint", "Third-party image should be pulled by fixed digest.")
    return Classification(clean, "manual-review", "operator-review", "Image has no trusted rebuild or registry rule.")


def _known_suffix(name: str, suffixes: dict[str, Any] | set[str]) -> str | None:
    for suffix in suffixes:
        if name == suffix or name.endswith(f"_{suffix}"):
            return suffix
    return None


def _repository(image: str) -> str:
    if "@" in image:
        return image.split("@", 1)[0]
    if ":" not in image:
        return image
    return image.rsplit(":", 1)[0]


def _read_names(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _as_dict(row: Classification) -> dict[str, str]:
    return {
        "name": row.name,
        "action": row.action,
        "destination": row.destination,
        "reason": row.reason,
    }


def _count_actions(rows: list[Classification]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.action] = counts.get(row.action, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    sys.exit(main())
