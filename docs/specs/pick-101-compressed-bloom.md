# Pick 101 - Compressed Bloom Filter

## Citation

Mitzenmacher, 2002, "Compressed Bloom Filters".

## Required Behavior

The native extension exposes a compact bit-packed Bloom filter with `add(item)` and `contains(item)`.

The structure stores bits in bytes rather than one Python object per bit and keeps false positives within expected smoke-test bounds for the configured size.

Benchmarks cover 100, 10,000, and 100,000 updates.
