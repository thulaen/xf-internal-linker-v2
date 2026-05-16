"""Find and prune disposable quality-run scratch folders safely."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

QUALITY_ARTIFACT_PREFIXES = (
    "mutmut-",
    "mutmut-debug-",
    "mutmut-list-",
    "coverage-",
    "pytest-debug-",
    "stryker-",
    "mull-",
    "fuzz-work-",
)
# The prune service validates this scratch root before deleting anything.
DEFAULT_QUALITY_ROOT = Path("/tmp")  # nosec B108


@dataclass(frozen=True, slots=True)
class ArtifactPruneResult:
    """One disposable folder selected by the quality artifact prune."""

    path: Path
    deleted: bool
    bytes_found: int


def find_quality_artifacts(root: Path = DEFAULT_QUALITY_ROOT) -> list[Path]:
    """Return immediate child folders that match known disposable prefixes."""
    root = root.resolve()
    _validate_prune_root(root)
    if not root.is_dir():
        return []
    return sorted(
        child
        for child in root.iterdir()
        if child.is_dir() and child.name.startswith(QUALITY_ARTIFACT_PREFIXES)
    )


def prune_quality_artifacts(
    *,
    root: Path = DEFAULT_QUALITY_ROOT,
    dry_run: bool = True,
) -> list[ArtifactPruneResult]:
    """Delete disposable quality folders; dry-run by default."""
    results: list[ArtifactPruneResult] = []
    for artifact in find_quality_artifacts(root):
        size = _directory_size(artifact)
        if dry_run:
            results.append(ArtifactPruneResult(artifact, False, size))
            continue
        _remove_tree(artifact)
        results.append(ArtifactPruneResult(artifact, True, size))
    return results


def _validate_prune_root(root: Path) -> None:
    if str(root) in {"/", "\\"}:
        raise ValueError("Refusing to prune from filesystem root")
    blocked_names = {
        "pgdata",
        "media_files",
        "staticfiles",
        "frontend_dist",
        "compiled_artifacts",
        "pyroscope_data",
        "loki_data",
        "alloy_data",
        "tempo_data",
        "grafana_data",
        "questdb_data",
    }
    if root.name in blocked_names:
        raise ValueError(f"Refusing to prune protected data store: {root.name}")


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _remove_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()
