#include <algorithm>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

class CountingBloomFilter {
   public:
    CountingBloomFilter(std::size_t counters, std::size_t hashes)
        : counters_(counters, 0), hashes_(hashes) {
        if (counters == 0 || hashes == 0) {
            throw std::invalid_argument("counters and hashes must be positive");
        }
    }

    void add(const std::string& item) {
        for (std::size_t i = 0; i < hashes_; ++i) {
            auto& counter = counters_[index(item, i)];
            if (counter < UINT16_MAX) {
                ++counter;
            }
        }
    }

    void remove(const std::string& item) {
        for (std::size_t i = 0; i < hashes_; ++i) {
            auto& counter = counters_[index(item, i)];
            if (counter > 0) {
                --counter;
            }
        }
    }

    bool contains(const std::string& item) const {
        for (std::size_t i = 0; i < hashes_; ++i) {
            if (counters_[index(item, i)] == 0) {
                return false;
            }
        }
        return true;
    }

    std::size_t counter_count() const { return counters_.size(); }
    std::size_t hash_count() const { return hashes_; }

   private:
    std::size_t index(const std::string& item, std::size_t salt) const {
        const auto mixed = item + "#" + std::to_string(salt * 0x9e3779b97f4a7c15ULL);
        return std::hash<std::string>{}(mixed) % counters_.size();
    }

    std::vector<std::uint16_t> counters_;
    std::size_t hashes_;
};

#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>

namespace py = pybind11;

PYBIND11_MODULE(counting_bloom, m) {
    py::class_<CountingBloomFilter>(m, "CountingBloomFilter")
        .def(py::init<std::size_t, std::size_t>())
        .def("add", &CountingBloomFilter::add)
        .def("remove", &CountingBloomFilter::remove)
        .def("contains", &CountingBloomFilter::contains)
        .def("counter_count", &CountingBloomFilter::counter_count)
        .def("hash_count", &CountingBloomFilter::hash_count);
}
#endif
