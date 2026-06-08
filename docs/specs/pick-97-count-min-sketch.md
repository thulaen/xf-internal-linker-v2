# Pick 97 - Count-Min Sketch

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-09-06]

## Citation

Cormode, G. and Muthukrishnan, S., 2005, "An Improved Data Stream Summary:
The Count-Min Sketch and its Applications", Journal of Algorithms 55(1):58-75.
doi:10.1016/j.jalgor.2003.12.001

[SPEC CITED: feature=pick-97-count-min-sketch kind=academic_paper id=10.1016/j.jalgor.2003.12.001 verified_at=2026-06-06]

## Required Behavior

The native extension exposes a fixed-width, fixed-depth Count-Min Sketch with
`add(item, count)` and `estimate(item)`.

The estimate must never undercount an inserted item. Collision overcounts are
expected and bounded by the chosen width and depth (Cormode & Muthukrishnan
2005, §3: the sketch yields a one-sided over-estimate of the true frequency).

Benchmarks cover 100, 10,000, and 100,000 updates.

## Public API (unchanged across the Rust port)

A single class `CountMinSketch`:

- `CountMinSketch(width: int, depth: int)` — positive `width` and `depth`;
  raises `ValueError("width and depth must be positive")` when either is 0.
- `add(item: str, count: int = 1) -> None` — adds one counter per row.
- `estimate(item: str) -> int` — returns the minimum counter across rows.
- `width() -> int`, `depth() -> int` — echo the constructor values.

## Rust port (2026-06-06): deliberate hashing decision

This kernel was ported from C++ (`backend/extensions/count_min_sketch.cpp`) to
Rust (`rust/extensions/count_min_sketch`) per RUST-FIRST.md and
`docs/PYTHON-RUST-MIGRATION-PLAN.md`. The C++ kernel indexed rows with
`std::hash<std::string>`, which is **libstdc++-implementation-defined** — the
exact counter values were never a portable, cross-language contract. A
repository-wide search found **zero Python callers** of `add`/`estimate`, so no
caller depends on specific hash outputs.

The Rust port therefore does NOT reproduce libstdc++'s hash byte-for-byte. It
reproduces the **behavioural contract** and keeps the same per-row salt-mixing
design as the C++ kernel:

- `index(item, row) = hash(item + "#" + (row * 0x94d049bb133111eb).to_string()) % width`
- The hash is a **fixed, deterministic** Rust hasher
  (`std::collections::hash_map::DefaultHasher`, the standard library's SipHash
  with fixed default keys), so estimates are reproducible across runs and across
  machines for a given build.
- The salt constant `0x94d049bb133111eb` is the SplitMix64/fmix mixing constant
  (Steele, Lea & Flood 2014, "Fast Splittable Pseudorandom Number Generators",
  OOPSLA 2014, doi:10.1145/2660193.2660195), used to decorrelate the row salts
  exactly as the C++ kernel did.

The behavioural contract the Rust port honours and tests:

1. **No undercount** — `estimate(item) >= true_count(item)` for every item.
2. **Deterministic** — identical insert streams produce identical estimates.
3. **Min-over-rows** — `estimate` returns the minimum, not the max or sum.
4. **Monotonic non-decreasing** — `estimate(item)` never falls as more of the
   same key is added.
5. **Unseen item** — `estimate` of a never-added item is `0`.
6. **Accessors** — `width()`/`depth()` echo the constructor arguments.
7. **Guard** — `width == 0` or `depth == 0` raises `ValueError`.
