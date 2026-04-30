#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

class CompressedBloomFilter {
public:
    CompressedBloomFilter(std::size_t bit_count, std::size_t hashes)
        : bits_((bit_count + 7) / 8, 0), bit_count_(bit_count), hashes_(hashes) {
        if (bit_count == 0 || hashes == 0) {
            throw std::invalid_argument("bit_count and hashes must be positive");
        }
    }

    void add(const std::string& item) {
        for (std::size_t i = 0; i < hashes_; ++i) {
            set_bit(index(item, i));
        }
    }

    bool contains(const std::string& item) const {
        for (std::size_t i = 0; i < hashes_; ++i) {
            if (!get_bit(index(item, i))) {
                return false;
            }
        }
        return true;
    }

    std::size_t bit_count() const { return bit_count_; }
    std::size_t byte_count() const { return bits_.size(); }
    std::size_t hash_count() const { return hashes_; }

private:
    std::size_t index(const std::string& item, std::size_t salt) const {
        const auto mixed = item + "#" + std::to_string(salt * 0x517cc1b727220a95ULL);
        return std::hash<std::string>{}(mixed) % bit_count_;
    }

    void set_bit(std::size_t bit) {
        bits_[bit / 8] |= static_cast<std::uint8_t>(1U << (bit % 8));
    }

    bool get_bit(std::size_t bit) const {
        return (bits_[bit / 8] & static_cast<std::uint8_t>(1U << (bit % 8))) != 0;
    }

    std::vector<std::uint8_t> bits_;
    std::size_t bit_count_;
    std::size_t hashes_;
};

#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>

namespace py = pybind11;

PYBIND11_MODULE(compressed_bloom, m) {
    py::class_<CompressedBloomFilter>(m, "CompressedBloomFilter")
        .def(py::init<std::size_t, std::size_t>())
        .def("add", &CompressedBloomFilter::add)
        .def("contains", &CompressedBloomFilter::contains)
        .def("bit_count", &CompressedBloomFilter::bit_count)
        .def("byte_count", &CompressedBloomFilter::byte_count)
        .def("hash_count", &CompressedBloomFilter::hash_count);
}
#endif
