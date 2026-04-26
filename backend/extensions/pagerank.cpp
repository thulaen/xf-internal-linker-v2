#ifndef XF_BENCH_MODE
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
namespace py = pybind11;
#endif
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <tuple>

#include "include/pagerank_core.h"

double pagerank_step_core(const int32_t *indptr_ptr, const int32_t *indices_ptr,
                          const double *data_ptr, const double *ranks_ptr,
                          const bool *dangling_ptr, double damping,
                          int node_count, double *next_ptr) {
  double dangling_mass = 0.0;

  for (int row = 0; row < node_count; ++row) {
    double link_mass = 0.0;
    for (int32_t idx = indptr_ptr[row]; idx < indptr_ptr[row + 1]; ++idx) {
      const int32_t col = indices_ptr[idx];
      link_mass += data_ptr[idx] * ranks_ptr[col];
    }
    next_ptr[row] = (1.0 - damping) * link_mass;
    if (dangling_ptr[row]) {
      dangling_mass += ranks_ptr[row];
    }
  }

  const double base_mass =
      ((1.0 - damping) * dangling_mass + damping) / node_count;
  double total_mass = 0.0;
  for (int row = 0; row < node_count; ++row) {
    next_ptr[row] += base_mass;
    total_mass += next_ptr[row];
  }

  for (int row = 0; row < node_count; ++row) {
    next_ptr[row] /= total_mass;
  }

  double delta = 0.0;
  for (int row = 0; row < node_count; ++row) {
    delta += std::abs(next_ptr[row] - ranks_ptr[row]);
  }

  return delta;
}

double personalized_pagerank_step_core(
    const int32_t *indptr_ptr, const int32_t *indices_ptr,
    const double *data_ptr, const double *ranks_ptr, const bool *dangling_ptr,
    const double *personalization_ptr, double damping, int node_count,
    double *next_ptr) {
  // PARITY: matches pagerank_step_core link-mass loop above —
  // link_mass[row] = Σ data[idx] * ranks[indices[idx]].
  double dangling_mass = 0.0;
  for (int row = 0; row < node_count; ++row) {
    double link_mass = 0.0;
    for (int32_t idx = indptr_ptr[row]; idx < indptr_ptr[row + 1]; ++idx) {
      const int32_t col = indices_ptr[idx];
      link_mass += data_ptr[idx] * ranks_ptr[col];
    }
    // PARITY: same (1-d)*link recurrence as uniform PageRank;
    // only the teleport step below differs.
    next_ptr[row] = (1.0 - damping) * link_mass;
    if (dangling_ptr[row]) {
      dangling_mass += ranks_ptr[row];
    }
  }

  // PARITY: replaces uniform 1/node_count teleport with vector
  // teleport. Standard PR formula:
  //     next[i] = (1-d)*link[i] + ((1-d)*dangling + d) / N
  // Personalized PR distributes that teleport mass by the
  // personalization vector p[i] (which the caller normalised to
  // sum to 1.0):
  //     next[i] = (1-d)*link[i] + ((1-d)*dangling + d) * p[i]
  // Equivalent to the Haveliwala 2002 §3 personalised recurrence.
  const double teleport_mass = (1.0 - damping) * dangling_mass + damping;
  double total_mass = 0.0;
  for (int row = 0; row < node_count; ++row) {
    next_ptr[row] += teleport_mass * personalization_ptr[row];
    total_mass += next_ptr[row];
  }

  // PARITY: same renormalisation as uniform PageRank — the
  // recurrence above is mass-conserving in theory, but floating-
  // point round-off means we re-divide by total_mass to keep the
  // L1 sum at exactly 1.0.
  if (total_mass > 0.0) {
    for (int row = 0; row < node_count; ++row) {
      next_ptr[row] /= total_mass;
    }
  }

  double delta = 0.0;
  for (int row = 0; row < node_count; ++row) {
    delta += std::abs(next_ptr[row] - ranks_ptr[row]);
  }
  return delta;
}

void hits_step_core(const int32_t *indptr_ptr, const int32_t *indices_ptr,
                    const double *data_ptr, const double *authority_ptr,
                    const double *hub_ptr, int node_count,
                    double *next_authority_ptr, double *next_hub_ptr) {
  // Zero the output vectors before deposit accumulation.
  // (Caller can't pre-zero portably across numpy / raw buffers, so
  // the kernel takes ownership.)
  for (int i = 0; i < node_count; ++i) {
    next_authority_ptr[i] = 0.0;
    next_hub_ptr[i] = 0.0;
  }

  // CSR convention: same as pagerank_step_core's input — row=target
  // (call it ``v``), col=source (``u``). Each entry represents an
  // edge ``u → v`` with weight ``data[idx]``.
  //
  // PARITY: weighted Kleinberg 1999 recurrence —
  //   for each edge u → v with weight w:
  //     next_authority[v] += w * hub[u]    (incoming hubs)
  //     next_hub[u]       += w * authority[v] (outgoing authorities)
  // Single CSR pass — outer loop walks targets v, inner loop reads
  // each source u that points at v. Both deposits land in O(|E|).
  for (int v = 0; v < node_count; ++v) {
    for (int32_t idx = indptr_ptr[v]; idx < indptr_ptr[v + 1]; ++idx) {
      const int32_t u = indices_ptr[idx];
      const double w = data_ptr[idx];
      // PARITY: authority[v] aggregates hub of nodes pointing at v.
      next_authority_ptr[v] += w * hub_ptr[u];
      // PARITY: hub[u] aggregates authority of nodes u points at.
      next_hub_ptr[u] += w * authority_ptr[v];
    }
  }
  // Normalisation + convergence checks happen in the Python driver
  // (see the upcoming Phase 5b wrappers in hits.py / personalized_pagerank.py)
  // — see the kernel header for why.
}

#ifndef XF_BENCH_MODE
std::tuple<py::array_t<double>, double> pagerank_step(
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indptr,
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indices,
    py::array_t<double, py::array::c_style | py::array::forcecast> data,
    py::array_t<double, py::array::c_style | py::array::forcecast> ranks,
    py::array_t<bool, py::array::c_style | py::array::forcecast> dangling_mask,
    double damping, int node_count) {
  auto indptr_buf = indptr.request();
  auto indices_buf = indices.request();
  auto data_buf = data.request();
  auto ranks_buf = ranks.request();
  auto dangling_buf = dangling_mask.request();

  if (indptr_buf.ndim != 1 || indices_buf.ndim != 1 || data_buf.ndim != 1 ||
      ranks_buf.ndim != 1 || dangling_buf.ndim != 1) {
    throw std::runtime_error("pagerank_step expects 1D CSR arrays and vectors");
  }
  if (node_count < 0) {
    throw std::runtime_error("node_count must be non-negative");
  }
  if (static_cast<size_t>(indptr_buf.shape[0]) !=
      static_cast<size_t>(node_count + 1)) {
    throw std::runtime_error("indptr length must be node_count + 1");
  }
  if (static_cast<size_t>(ranks_buf.shape[0]) !=
      static_cast<size_t>(node_count)) {
    throw std::runtime_error("ranks length must equal node_count");
  }
  if (static_cast<size_t>(dangling_buf.shape[0]) !=
      static_cast<size_t>(node_count)) {
    throw std::runtime_error("dangling_mask length must equal node_count");
  }
  if (indices_buf.shape[0] != data_buf.shape[0]) {
    throw std::runtime_error("indices and data must have the same length");
  }

  auto next_ranks = py::array_t<double>(node_count);
  auto next_buf = next_ranks.request();

  double delta;
  {
    py::gil_scoped_release release;
    delta =
        pagerank_step_core(static_cast<const int32_t *>(indptr_buf.ptr),
                           static_cast<const int32_t *>(indices_buf.ptr),
                           static_cast<const double *>(data_buf.ptr),
                           static_cast<const double *>(ranks_buf.ptr),
                           static_cast<const bool *>(dangling_buf.ptr), damping,
                           node_count, static_cast<double *>(next_buf.ptr));
  }

  return std::make_tuple(next_ranks, delta);
}

std::tuple<py::array_t<double>, double> personalized_pagerank_step(
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indptr,
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indices,
    py::array_t<double, py::array::c_style | py::array::forcecast> data,
    py::array_t<double, py::array::c_style | py::array::forcecast> ranks,
    py::array_t<bool, py::array::c_style | py::array::forcecast> dangling_mask,
    py::array_t<double, py::array::c_style | py::array::forcecast>
        personalization,
    double damping, int node_count) {
  auto indptr_buf = indptr.request();
  auto indices_buf = indices.request();
  auto data_buf = data.request();
  auto ranks_buf = ranks.request();
  auto dangling_buf = dangling_mask.request();
  auto personalization_buf = personalization.request();

  if (indptr_buf.ndim != 1 || indices_buf.ndim != 1 || data_buf.ndim != 1 ||
      ranks_buf.ndim != 1 || dangling_buf.ndim != 1 ||
      personalization_buf.ndim != 1) {
    throw std::runtime_error(
        "personalized_pagerank_step expects 1D CSR arrays and vectors");
  }
  if (node_count < 0) {
    throw std::runtime_error("node_count must be non-negative");
  }
  if (static_cast<size_t>(indptr_buf.shape[0]) !=
      static_cast<size_t>(node_count + 1)) {
    throw std::runtime_error("indptr length must be node_count + 1");
  }
  if (static_cast<size_t>(ranks_buf.shape[0]) !=
      static_cast<size_t>(node_count)) {
    throw std::runtime_error("ranks length must equal node_count");
  }
  if (static_cast<size_t>(dangling_buf.shape[0]) !=
      static_cast<size_t>(node_count)) {
    throw std::runtime_error("dangling_mask length must equal node_count");
  }
  if (static_cast<size_t>(personalization_buf.shape[0]) !=
      static_cast<size_t>(node_count)) {
    throw std::runtime_error("personalization length must equal node_count");
  }
  if (indices_buf.shape[0] != data_buf.shape[0]) {
    throw std::runtime_error("indices and data must have the same length");
  }

  auto next_ranks = py::array_t<double>(node_count);
  auto next_buf = next_ranks.request();

  double delta;
  {
    py::gil_scoped_release release;
    delta = personalized_pagerank_step_core(
        static_cast<const int32_t *>(indptr_buf.ptr),
        static_cast<const int32_t *>(indices_buf.ptr),
        static_cast<const double *>(data_buf.ptr),
        static_cast<const double *>(ranks_buf.ptr),
        static_cast<const bool *>(dangling_buf.ptr),
        static_cast<const double *>(personalization_buf.ptr), damping,
        node_count, static_cast<double *>(next_buf.ptr));
  }

  return std::make_tuple(next_ranks, delta);
}

std::tuple<py::array_t<double>, py::array_t<double>> hits_step(
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indptr,
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indices,
    py::array_t<double, py::array::c_style | py::array::forcecast> data,
    py::array_t<double, py::array::c_style | py::array::forcecast> authority,
    py::array_t<double, py::array::c_style | py::array::forcecast> hub,
    int node_count) {
  auto indptr_buf = indptr.request();
  auto indices_buf = indices.request();
  auto data_buf = data.request();
  auto authority_buf = authority.request();
  auto hub_buf = hub.request();

  if (indptr_buf.ndim != 1 || indices_buf.ndim != 1 || data_buf.ndim != 1 ||
      authority_buf.ndim != 1 || hub_buf.ndim != 1) {
    throw std::runtime_error("hits_step expects 1D CSR arrays and vectors");
  }
  if (node_count < 0) {
    throw std::runtime_error("node_count must be non-negative");
  }
  if (static_cast<size_t>(indptr_buf.shape[0]) !=
      static_cast<size_t>(node_count + 1)) {
    throw std::runtime_error("indptr length must be node_count + 1");
  }
  if (static_cast<size_t>(authority_buf.shape[0]) !=
      static_cast<size_t>(node_count)) {
    throw std::runtime_error("authority length must equal node_count");
  }
  if (static_cast<size_t>(hub_buf.shape[0]) !=
      static_cast<size_t>(node_count)) {
    throw std::runtime_error("hub length must equal node_count");
  }
  if (indices_buf.shape[0] != data_buf.shape[0]) {
    throw std::runtime_error("indices and data must have the same length");
  }

  auto next_authority = py::array_t<double>(node_count);
  auto next_hub = py::array_t<double>(node_count);
  auto next_authority_buf = next_authority.request();
  auto next_hub_buf = next_hub.request();

  {
    py::gil_scoped_release release;
    hits_step_core(static_cast<const int32_t *>(indptr_buf.ptr),
                   static_cast<const int32_t *>(indices_buf.ptr),
                   static_cast<const double *>(data_buf.ptr),
                   static_cast<const double *>(authority_buf.ptr),
                   static_cast<const double *>(hub_buf.ptr), node_count,
                   static_cast<double *>(next_authority_buf.ptr),
                   static_cast<double *>(next_hub_buf.ptr));
  }

  return std::make_tuple(next_authority, next_hub);
}

PYBIND11_MODULE(pagerank, m) {
  m.def("pagerank_step", &pagerank_step,
        "Run one weighted PageRank iteration step from CSR inputs");
  m.def(
      "personalized_pagerank_step", &personalized_pagerank_step,
      "Run one personalised (seeded) PageRank iteration step from CSR inputs.");
  m.def("hits_step", &hits_step,
        "Run one Kleinberg HITS iteration step (authority + hub) from forward "
        "CSR.");
}
#endif
