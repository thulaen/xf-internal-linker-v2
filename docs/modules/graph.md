# Module: graph

**Layer:** 2 (business).
**Status:** Stub — full detail lands in slice 8 (lands alongside `analytics`).
**Maps to today:** link-graph storage, PageRank computation, node-affinity scoring, the graph fitness checks, the D3 visualization data feed.

## Plain-English summary

The graph module owns the internal link graph: which content links to which content, the PageRank-style ranks the linker uses as a signal, the per-node affinity scores, and the data shapes that the Angular visualization reads. The graph data is derived from applied suggestions plus existing internal links the connectors observed.

If a function asks "what links to what, and how strongly," it belongs here.

## Public interface

`graph.api` exports the read surface plus the rebuild verbs. Examples slated for slice 8:

- `Node`, `Edge`
- `node_rank(content_id: int) -> float`
- `affinity(source_id: int, target_id: int) -> float`
- `iter_edges(content_id: int) -> Iterable[Edge]`
- `rebuild_graph()` (Celery job entry point exposed as a verb)
- `graph_fitness_check()` (returns a small report; called by `governance`)

PageRank internals, sparse-matrix code, and the D3 data shaper are private.

## Job (the "and"-test)

Graph owns one job: **the link graph and the ranks derived from it.** It does not own which posts exist (`content`), how a candidate is scored (`pipeline` reads from `graph.api`), or how a human reviews a link (`suggestions`).

## Owned tables

- `LinkGraphNode`, `LinkGraphEdge`
- `NodeRank` (per-node PageRank value, versioned per the no-duplicates rule)
- `GraphFitnessSnapshot`

The full list arrives with the slice-8 move.

## Dependencies

- `platform` (hardware profile, disk-pressure)
- `content` (resolve content IDs to nodes)

Graph does **not** depend on `pipeline`, `suggestions`, `analytics`, `operations`, `governance` directly.

## Open questions

- PageRank is run on a Celery schedule — confirm the schedule and the disk-pressure pre-flight live inside `graph`, not in `operations`.
- The D3 visualization reads a derived JSON shape. Confirm the shape lives in `graph.api` (so the Angular consumer is a true downstream reader), not in a separate "viz" sub-module.

## Citations

- Brin & Page 1998 — *The Anatomy of a Large-Scale Hypertextual Web Search Engine.* (PageRank.)
- Kleinberg 1999 — HITS (used as a secondary signal in node affinity).

## Slice that moves this module

Slice 8 (with `analytics`). Lands after `pipeline` and `suggestions`.
