#pragma once
#include <cstddef>
#include <cstdint>

// One iteration of weighted PageRank from a CSR adjacency matrix
// (row=target, col=source — see weighted_pagerank.py:_load_weighted_graph).
//
// Convention note: in this codebase ``damping`` is the **teleport
// probability** (textbook ``1 - alpha``, default ~0.15) — the OPPOSITE
// of networkx's ``alpha`` parameter (link-following probability,
// default ~0.85). The Python wrapper converts: ``damping = 1 - alpha``.
//
// Returns ``delta`` = Σ |next - prev|, the L1 change in the rank
// vector. Caller drives the convergence loop; converges when
// ``delta <= node_count * tol``.
double pagerank_step_core(const int32_t* indptr, const int32_t* indices, const double* data,
                          const double* ranks, const bool* dangling_mask, double damping,
                          int node_count, double* out_next_ranks);

// One iteration of personalized (seeded) PageRank — pick #36 / #30.
//
// Same shape as ``pagerank_step_core`` but the teleport mass is
// distributed by the ``personalization`` vector instead of uniformly.
// ``personalization`` must be a length-``node_count`` array that sums
// to 1.0 (caller's responsibility); zeros on non-seed nodes are how
// you concentrate teleport mass on the seed set.
//
// Reduces to standard PageRank when personalization[i] = 1/node_count
// for every i (same numerics within rounding).
//
// Returns ``delta`` = Σ |next - prev|.
double personalized_pagerank_step_core(const int32_t* indptr, const int32_t* indices,
                                       const double* data, const double* ranks,
                                       const bool* dangling_mask, const double* personalization,
                                       double damping, int node_count, double* out_next_ranks);

// One iteration of Kleinberg HITS — pick #29.
//
// CSR convention: same as ``pagerank_step_core`` — ``row=target``
// (``v``), ``indices[idx]=source`` (``u``), ``data[idx]=weight``.
// Each non-zero entry is an edge ``u → v``. For every such edge the
// kernel deposits:
//
//   next_authority[v] += weight * hub[u]      (v's incoming hubs)
//   next_hub[u]       += weight * authority[v] (u's outgoing authorities)
//
// — the weighted Kleinberg 1999 recurrence.
//
// This kernel does NOT normalise — the caller drives normalisation
// (typically L1 sum-to-1 after each iteration) plus convergence
// checks. Keeping normalisation in Python lets tests compare against
// any normalisation scheme without a C++ rebuild.
//
// ``out_next_authority`` and ``out_next_hub`` must be pre-allocated
// length-``node_count`` arrays. They are zeroed inside the function
// before deposits accumulate.
void hits_step_core(const int32_t* indptr, const int32_t* indices, const double* data,
                    const double* authority, const double* hub, int node_count,
                    double* out_next_authority, double* out_next_hub);
