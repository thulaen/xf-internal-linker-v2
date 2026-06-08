# Pick 100 - Counting Bloom Filter

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-09-06]

## Citation

Fan, L., Cao, P., Almeida, J. and Broder, A.Z., 2000, "Summary Cache: A Scalable
Wide-Area Web Cache Sharing Protocol", IEEE/ACM Transactions on Networking
8(3):281-293. doi:10.1109/90.851975

Bloom, B.H., 1970, "Space/Time Trade-offs in Hash Coding with Allowable Errors",
Communications of the ACM 13(7):422-426. doi:10.1145/362686.362692

[SPEC CITED: feature=pick-100-counting-bloom kind=academic_paper id=10.1109/90.851975 verified_at=2026-06-06]

## Required Behavior

The native extension exposes a fixed-size counting Bloom filter with
`add(item)`, `remove(item)`, and `contains(item)`.

A counting Bloom filter (Fan et al. 2000) replaces a plain Bloom filter's bit
array with an array of small counters. `add` increments one counter per hash
function; `remove` decrements them; `contains` reports membership — true iff
every indexed counter is non-zero. The counters let the structure support
deletion, which a plain Bloom filter (Bloom 1970) cannot.

The guarantees:

- **No false negatives** while an item is net-present. Deletes decrement
  counters without underflow; counter saturation must not wrap around (either
  would turn a present item into an apparent absent one).
- **False positives are expected** and bounded by the chosen counter count and
  hash count. The contract is the no-false-negative direction, not a specific
  false-positive rate.

Benchmarks cover 100, 10,000, and 100,000 updates.

## Public API (unchanged across the Rust port)

A single class `CountingBloomFilter`:

- `CountingBloomFilter(counters: int, hashes: int)` — positive `counters` and
  `hashes`; raises `ValueError("counters and hashes must be positive")` when
  either is 0.
- `add(item: str) -> None` — increment one counter per hash function
  (saturating at 65535).
- `remove(item: str) -> None` — decrement one counter per hash function
  (flooring at 0).
- `contains(item: str) -> bool` — true iff every indexed counter is non-zero.
- `counter_count() -> int`, `hash_count() -> int` — echo the constructor values.

## Rust port (2026-06-06): deliberate hashing decision

This kernel was ported from C++ (`backend/extensions/counting_bloom.cpp`) to
Rust (`rust/extensions/counting_bloom`) per RUST-FIRST.md and
`docs/PYTHON-RUST-MIGRATION-PLAN.md`. The C++ kernel indexed counters with
`std::hash<std::string>`, which is **libstdc++-implementation-defined** — the
exact counter-to-index mapping was never a portable, cross-language contract. A
repository-wide search found **zero Python callers** of
`add`/`remove`/`contains`, so no caller depends on specific hash outputs.

The Rust port therefore does NOT reproduce libstdc++'s hash byte-for-byte. It
reproduces the **behavioural contract** and keeps the same per-hash salt-mixing
design as the C++ kernel:

- `index(item, salt) = hash(item + "#" + (salt * 0x9e3779b97f4a7c15).to_string()) % counters`
- The hash is a **fixed, deterministic** Rust hasher
  (`std::collections::hash_map::DefaultHasher`, the standard library's SipHash
  with fixed default keys), so results are reproducible across runs and across
  machines for a given build.
- The salt constant `0x9e3779b97f4a7c15` is the 64-bit golden-ratio
  (fibonacci-hashing) constant (Knuth, "The Art of Computer Programming",
  Vol. 3, §6.4), used to decorrelate the per-hash salts exactly as the C++
  kernel did.
- The counters are `u16` (matching the C++ width). `add` uses saturating
  addition (caps at 65535, never wraps) and `remove` uses saturating
  subtraction (floors at 0, never underflows), exactly the C++ semantics —
  these are part of the behavioural contract (preventing false negatives), not
  hash-dependent.

The behavioural contract the Rust port honours and tests:

1. **No false negatives** — a net-present item (added with no balancing
   `remove`) is always `contains`-true.
2. **Deletion support** — `add` then balancing `remove` of a collision-free key
   returns `contains` to false.
3. **Saturating increment** — adding past 65535 never wraps to a false negative.
4. **Flooring decrement** — `remove` of a never-added item is a safe no-op.
5. **Unseen item** — a never-touched item is not contained.
6. **Deterministic** — identical construction + insert stream yields identical
   `contains` / `counter_count` / `hash_count` across filters and runs.
7. **Accessors** — `counter_count()` / `hash_count()` echo the constructor.
8. **Guard** — `counters == 0` or `hashes == 0` raises `ValueError`.
