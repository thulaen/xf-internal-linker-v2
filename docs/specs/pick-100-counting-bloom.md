# Pick 100 - Counting Bloom Filter

## Citation

Fan et al., 2000, "Summary Cache: A Scalable Wide-Area Web Cache Sharing Protocol".

## Required Behavior

The native extension exposes a counting Bloom filter with `add(item)`, `remove(item)`, and `contains(item)`.

Deletes decrement counters without underflow. Counter saturation must not wrap around.

Benchmarks cover 100, 10,000, and 100,000 updates.
