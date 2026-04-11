#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;
#endif
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

/**
 * A thread-safe string pool for token interning.
 * Reduces memory overhead when dealing with millions of tokens.
 */
class StringPool {
   public:
    uint32_t intern(const std::string& str) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = string_to_id_.find(str);
        if (it != string_to_id_.end()) {
            return it->second;
        }
        uint32_t id = static_cast<uint32_t>(id_to_string_.size());
        id_to_string_.push_back(str);
        string_to_id_[str] = id;
        return id;
    }

    std::string get(uint32_t id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        if (id < id_to_string_.size()) {
            return id_to_string_[id];
        }
        return "";
    }

    size_t size() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return id_to_string_.size();
    }

    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        id_to_string_.clear();
        string_to_id_.clear();
    }

   private:
    mutable std::mutex mutex_;
    std::vector<std::string> id_to_string_;
    std::unordered_map<std::string, uint32_t> string_to_id_;
};

#ifndef XF_BENCH_MODE
PYBIND11_MODULE(strpool, m) {
    py::class_<StringPool>(m, "StringPool")
        .def(py::init<>())
        .def("intern", &StringPool::intern, "Intern a string and return its unique ID")
        .def("get", &StringPool::get, "Get the string associated with an ID")
        .def("size", &StringPool::size, "Get the number of unique strings in the pool")
        .def("clear", &StringPool::clear, "Clear the pool");
}
#endif
