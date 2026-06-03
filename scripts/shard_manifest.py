"""
Deterministic shard manifest generator.

Implements Hamilton / largest-remainder integer distribution so that
distribute_shards(n, weights) always returns integers that sum exactly to n.

References:
  Balinski & Young 1982 — Fair Representation (ISBN 978-0815710103)
  Hamilton method (largest-remainder) for apportionment.
"""

from __future__ import annotations

from typing import Sequence


STORAGE_PLACEMENT = "mint"

PROFILES: dict[str, dict] = {
    "2m": {
        "nodes": ["windows", "mint"],
        "weights": [65, 35],
    },
    "3m_one_strong": {
        "nodes": ["strong", "weak1", "weak2"],
        "weights": [58, 31, 31],
    },
    "3m_two_strong": {
        "nodes": ["strong1", "strong2", "weak"],
        "weights": [49, 49, 22],
    },
}


class ShardManifest:
    """Holds the per-node shard allocation for one run."""

    def __init__(self, profile: str, n_shards: int, allocation: dict[str, int] | None = None) -> None:
        self.profile = profile
        self.n_shards = n_shards
        self.allocation: dict[str, int] = allocation if allocation is not None else {}

    def total(self) -> int:
        return sum(self.allocation.values())


def distribute_shards(n_shards: int, weights: Sequence[int]) -> list[int]:
    """Return integers that sum exactly to n_shards, distributed by weights.

    Uses the Hamilton (largest-remainder) method so remainders are assigned
    one-at-a-time to the nodes with the largest fractional parts.

    Args:
        n_shards: Total shards to distribute. Must be >= 0.
        weights:  Relative weights for each node. Must be non-empty with
                  a positive sum.

    Raises:
        ValueError: If n_shards < 0, weights is empty, or sum(weights) == 0.
    """
    if n_shards < 0:
        raise ValueError(f"n_shards must be >= 0, got {n_shards}")
    if not weights:
        raise ValueError("weights must be non-empty")
    total_weight = sum(weights)
    if total_weight == 0:
        raise ValueError("sum(weights) must be > 0")

    if n_shards == 0:
        return [0] * len(weights)

    exact = [(w / total_weight) * n_shards for w in weights]
    floors = [int(q) for q in exact]
    remainder = n_shards - sum(floors)

    order = sorted(
        range(len(weights)),
        key=lambda i: exact[i] - floors[i],
        reverse=True,
    )
    for i in order[:remainder]:
        floors[i] += 1

    return floors


def generate_manifest(profile: str, n_shards: int) -> ShardManifest:
    """Build a ShardManifest for the given profile and total shard count.

    Args:
        profile:  Key in PROFILES (e.g. "2m", "3m_one_strong").
        n_shards: Total shards to distribute across nodes.

    Raises:
        KeyError: If profile is not in PROFILES.
        ValueError: Propagated from distribute_shards on invalid n_shards.
    """
    cfg = PROFILES[profile]
    nodes: list[str] = cfg["nodes"]
    weights: list[int] = cfg["weights"]

    counts = distribute_shards(n_shards, weights)
    allocation = dict(zip(nodes, counts))

    return ShardManifest(profile=profile, n_shards=n_shards, allocation=allocation)
