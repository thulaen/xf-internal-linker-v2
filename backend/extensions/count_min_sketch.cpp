#include <algorithm>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

class CountMinSketch {
public:
    CountMinSketch(std::size_t width, std::size_t depth)
        : table_(width * depth, 0), width_(width), depth_(depth) {
        if (width == 0 || depth == 0) {
            throw std::invalid_argument("width and depth must be positive");
        }
    }

    void add(const std::string& item, std::uint64_t count = 1) {
        for (std::size_t row = 0; row < depth_; ++row) {
            table_[row * width_ + index(item, row)] += count;
        }
    }

    std::uint64_t estimate(const std::string& item) const {
        std::uint64_t best = UINT64_MAX;
        for (std::size_t row = 0; row < depth_; ++row) {
            best = std::min(best, table_[row * width_ + index(item, row)]);
        }
        return best == UINT64_MAX ? 0 : best;
    }

    std::size_t width() const { return width_; }
    std::size_t depth() const { return depth_; }

private:
    std::size_t index(const std::string& item, std::size_t salt) const {
        const auto mixed = item + "#" + std::to_string(salt * 0x94d049bb133111ebULL);
        return std::hash<std::string>{}(mixed) % width_;
    }

    std::vector<std::uint64_t> table_;
    std::size_t width_;
    std::size_t depth_;
};

#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>

namespace py = pybind11;

PYBIND11_MODULE(count_min_sketch, m) {
    py::class_<CountMinSketch>(m, "CountMinSketch")
        .def(py::init<std::size_t, std::size_t>())
        .def("add", &CountMinSketch::add, py::arg("item"), py::arg("count") = 1)
        .def("estimate", &CountMinSketch::estimate)
        .def("width", &CountMinSketch::width)
        .def("depth", &CountMinSketch::depth);
}
#endif
