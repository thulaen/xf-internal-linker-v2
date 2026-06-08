# papertrail_dedup (Rust kernel)

Paper-trail **MinHash + LSH** near-duplicate index. Ported from the C++ kernel
`backend/extensions/papertrail_dedup.cpp` to Rust per
[`docs/PYTHON-RUST-MIGRATION-PLAN.md`](../../../docs/PYTHON-RUST-MIGRATION-PLAN.md)
and [`RUST-FIRST.md`](../../../RUST-FIRST.md) (zero Python fallback).

Ships as `papertrail_dedup.so`, imported as `extensions.papertrail_dedup`. The
single bound symbol is the class `DedupIndex`.

## What it does

Each text gets a 64-component MinHash signature built from 5-character shingles
and a 2-universal hash family. Signatures are banded (8 bands × 8 rows) into 8
locality-sensitive-hashing band indexes so `find_similar` only compares Jaccard
resemblance against band-collision candidates. Supports idempotent `add_entry` /
`remove_entry`, a Jaccard-threshold similarity query, and an atomic binary
snapshot (`save` / `load`).

The MinHash math, the 2-universal family seeding (a vendored `mt19937_64`), the
FNV band reduction, and the binary snapshot layout reproduce the C++ kernel
**exactly**, so a snapshot written by either implementation reloads on the
other.

Sources: Broder 1997 (MinHash); Indyk & Motwani 1998 (LSH, STOC); Leskovec,
Rajaraman & Ullman, *Mining of Massive Datasets* 3rd ed. Ch. 3 (banding
b=8, r=8, m=64, shingle width k=5).
