"""Reservoir sampling — Vitter's Algorithm R (1985).

Reference
---------
Vitter, J. S. (1985). "Random sampling with a reservoir." *ACM
Transactions on Mathematical Software* 11(1): 37-57.

Goal
----
Draw a uniformly-random sample of fixed size ``k`` from a stream of
unknown (possibly very large) length, using only ``O(k)`` memory.
Every item that goes past has an equal chance of ending up in the
final reservoir — no bias toward early or late items.

Vitter's **Algorithm R** (the "basic" reservoir method):

1. Fill the reservoir with the first ``k`` items.
2. For the ``i``-th item after that (``i > k``), pick a uniform random
   index ``j ∈ [0, i-1]``. If ``j < k``, replace ``reservoir[j]`` with
   the new item; otherwise discard it.

Intuition: at step ``i``, each of the ``i`` seen items must have an
equal ``k/i`` chance of being in the reservoir. The replacement
probability works out exactly.

Usage
-----
The linker fires this from the scheduled
``reservoir_sampling_rotate`` job: rolling through the day's
suggestion stream to build a fair eval sample for offline NDCG
and precision-at-k measurements. Also used by the diagnostics
"random spot-check" tab.

The module is pure Python; a ``random.Random`` instance can be
passed in so tests get deterministic sampling without patching
``random``. No NumPy, no Django.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Hashable, Iterable, Iterator, TypeVar

T = TypeVar("T")


@dataclass
class Reservoir:
    """Streaming reservoir sampler.

    Callers feed items in via :meth:`add`. The current sample is
    always available on :attr:`items` (a plain list — read-only as
    far as the caller is concerned). After an arbitrary number of
    ``add`` calls the reservoir holds a uniformly random subset of
    size up to ``k``.
    """

    k: int
    items: list = field(default_factory=list)
    _seen: int = 0
    _rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise ValueError("k must be > 0")

    @property
    def observation_count(self) -> int:
        """How many items have been shown to :meth:`add` so far."""
        return self._seen

    def add(self, item) -> None:
        """Feed one *item* into the sampler. ``O(1)``."""
        self._seen += 1
        if len(self.items) < self.k:
            self.items.append(item)
            return
        # Fast-path: random index into the first ``_seen`` items.
        j = self._rng.randrange(self._seen)
        if j < self.k:
            self.items[j] = item

    def extend(self, stream: Iterable) -> None:
        """Feed every element of *stream* into the sampler."""
        for item in stream:
            self.add(item)

    def snapshot(self) -> list:
        """Return a defensive copy of the current sample."""
        return list(self.items)


def sample(
    stream: Iterable[T],
    *,
    k: int,
    rng: random.Random | None = None,
) -> list[T]:
    """Return a size-*k* reservoir sample of *stream*.

    Convenience wrapper for the one-shot case: hand in an iterable,
    get back a list. For long-running stream consumption that updates
    the sample over time, use :class:`Reservoir` directly.

    Empty streams return an empty list. Streams shorter than ``k``
    return every observed item.

    Raises
    ------
    ValueError
        If ``k`` <= 0.
    """
    reservoir = Reservoir(k=k, _rng=rng or random.Random())
    reservoir.extend(stream)
    return reservoir.snapshot()


def deterministic_rng(seed: int) -> random.Random:
    """Return a fresh :class:`random.Random` seeded at *seed*.

    Provided so callers can obtain reproducible sampling without
    reaching into the ``random`` module (patching the global RNG
    breaks other users; a dedicated ``Random`` instance doesn't).
    """
    return random.Random(seed)


def fair_shuffle(
    items: Iterable[Hashable],
    *,
    rng: random.Random | None = None,
) -> Iterator[Hashable]:
    """Stream *items* back in a uniformly-random order.

    Not strictly reservoir sampling — it's the finite-collection
    sibling. Useful for "present the eval set in random order so
    review fatigue doesn't bias late items". Lives here because
    it's part of the same "sample fairly from a sequence" toolbox.
    """
    materialised = list(items)
    local_rng = rng or random.Random()
    local_rng.shuffle(materialised)
    yield from materialised
