#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <tuple>
#include <stdexcept>

namespace py = pybind11;

std::tuple<py::array_t<double>, double> pagerank_step(
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indptr,
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> indices,
    py::array_t<double, py::array::c_style | py::array::forcecast> data,
    py::array_t<double, py::array::c_style | py::array::forcecast> ranks,
    py::array_t<bool, py::array::c_style | py::array::forcecast> dangling_mask,
    double damping,
    int node_count
) {
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
    if (static_cast<size_t>(indptr_buf.shape[0]) != static_cast<size_t>(node_count + 1)) {
        throw std::runtime_error("indptr length must be node_count + 1");
    }
    if (static_cast<size_t>(ranks_buf.shape[0]) != static_cast<size_t>(node_count)) {
        throw std::runtime_error("ranks length must equal node_count");
    }
    if (static_cast<size_t>(dangling_buf.shape[0]) != static_cast<size_t>(node_count)) {
        throw std::runtime_error("dangling_mask length must equal node_count");
    }
    if (indices_buf.shape[0] != data_buf.shape[0]) {
        throw std::runtime_error("indices and data must have the same length");
    }

    const auto* indptr_ptr = static_cast<const int32_t*>(indptr_buf.ptr);
    const auto* indices_ptr = static_cast<const int32_t*>(indices_buf.ptr);
    const auto* data_ptr = static_cast<const double*>(data_buf.ptr);
    const auto* ranks_ptr = static_cast<const double*>(ranks_buf.ptr);
    const auto* dangling_ptr = static_cast<const bool*>(dangling_buf.ptr);

    auto next_ranks = py::array_t<double>(node_count);
    auto next_buf = next_ranks.request();
    auto* next_ptr = static_cast<double*>(next_buf.ptr);

    double dangling_mass = 0.0;
    {
        py::gil_scoped_release release;

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

        const double base_mass = ((1.0 - damping) * dangling_mass + damping) / node_count;
        double total_mass = 0.0;
        for (int row = 0; row < node_count; ++row) {
            next_ptr[row] += base_mass;
            total_mass += next_ptr[row];
        }

        for (int row = 0; row < node_count; ++row) {
            next_ptr[row] /= total_mass;
        }
    }

    double delta = 0.0;
    for (int row = 0; row < node_count; ++row) {
        delta += std::abs(next_ptr[row] - ranks_ptr[row]);
    }

    return std::make_tuple(next_ranks, delta);
}

PYBIND11_MODULE(pagerank, m) {
    m.def(
        "pagerank_step",
        &pagerank_step,
        "Run one weighted PageRank iteration step from CSR inputs"
    );
}
