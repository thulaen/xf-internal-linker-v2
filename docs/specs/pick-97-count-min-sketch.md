# Pick 97 - Count-Min Sketch

## Citation

Cormode and Muthukrishnan, 2005, "An Improved Data Stream Summary: The Count-Min Sketch and its Applications".

## Required Behavior

The native extension exposes a fixed-width, fixed-depth Count-Min Sketch with `add(item, count)` and `estimate(item)`.

The estimate must never undercount an inserted item. Collision overcounts are expected and bounded by the chosen width and depth.

Benchmarks cover 100, 10,000, and 100,000 updates.
