// lesson_index.cpp — three-sub-index in-process cache.
//
// THIS COMMIT (Day 1 scaffold): correct contract via std::map / std::unordered_map.
// FOLLOW-UP: swap the std backings for ART (Leis 2013), Cuckoo (Pagh-Rodler 2001),
// and Robin Hood (Celis-Larson-Munro 1985) without changing the public API.
// The tests in tests/test_lesson_index.cpp and the Pybind11 binding below
// pin the contract so the swap is mechanical.
//
// Sources of truth (full citations in docs/specs/lesson-index.md):
//   Leis, Kemper, Neumann (2013). The Adaptive Radix Tree. ICDE.
//   Pagh & Rodler (2001). Cuckoo Hashing. ESA.
//   Celis, Larson, Munro (1985). Robin Hood Hashing. FOCS.
//   Evans (2006). jemalloc. BSDcan.
//   RFC 3309 — CRC-32C checksum.

#include "include/lesson_index.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <fstream>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <stdexcept>
#include <unordered_map>
#include <vector>

#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;
#endif

namespace xf::lesson_index {

namespace {

// ── CRC-32C (RFC 3309 Castagnoli) ─────────────────────────────────
std::uint32_t crc32c_table_(std::uint8_t byte) noexcept {
  static constexpr std::uint32_t kPoly = 0x82F63B78u;  // reversed 0x1EDC6F41
  std::uint32_t crc = byte;
  for (int i = 0; i < 8; ++i) {
    crc = (crc >> 1) ^ (kPoly & -(static_cast<std::int32_t>(crc & 1u)));
  }
  return crc;
}

std::int64_t now_unix_ns_() noexcept {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::system_clock::now().time_since_epoch())
      .count();
}

}  // namespace

std::uint32_t crc32c(const std::uint8_t* data, std::size_t len) noexcept {
  if (len == 0 || data == nullptr) return 0u;
  std::uint32_t crc = 0xFFFFFFFFu;
  for (std::size_t i = 0; i < len; ++i) {
    crc = (crc >> 8) ^ crc32c_table_(static_cast<std::uint8_t>((crc ^ data[i]) & 0xFFu));
  }
  return crc ^ 0xFFFFFFFFu;
}

// ── Snapshot helpers (shared by all three sub-indices) ────────────
namespace {

struct SnapshotHeader {
  std::uint32_t magic;
  std::uint32_t version;
  std::uint64_t payload_size;
  std::uint32_t crc32c_payload;
  std::uint32_t reserved;
};
static_assert(sizeof(SnapshotHeader) == 24, "header layout drift");

void write_snapshot_(const std::filesystem::path& path,
                     const std::vector<std::uint8_t>& payload) {
  std::filesystem::path tmp = path;
  tmp += ".tmp";
  {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
    if (!out) {
      throw std::runtime_error(
          "lesson_index: cannot open snapshot for write: " + tmp.string());
    }
    SnapshotHeader hdr{kSnapshotMagic, kSnapshotVersion,
                       static_cast<std::uint64_t>(payload.size()),
                       crc32c(payload.data(), payload.size()), 0u};
    out.write(reinterpret_cast<const char*>(&hdr), sizeof hdr);
    if (!payload.empty()) {
      out.write(reinterpret_cast<const char*>(payload.data()),
                static_cast<std::streamsize>(payload.size()));
    }
  }
  std::filesystem::rename(tmp, path);
}

std::vector<std::uint8_t> read_snapshot_(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("lesson_index: cannot open snapshot for read: " +
                             path.string());
  }
  SnapshotHeader hdr{};
  in.read(reinterpret_cast<char*>(&hdr), sizeof hdr);
  if (!in || hdr.magic != kSnapshotMagic) {
    throw std::runtime_error(
        "lesson_index: snapshot magic mismatch (corrupt or wrong format): " +
        path.string());
  }
  if (hdr.version != kSnapshotVersion) {
    throw std::runtime_error("lesson_index: snapshot version " +
                             std::to_string(hdr.version) + " unsupported: " +
                             path.string());
  }
  std::vector<std::uint8_t> payload(hdr.payload_size);
  if (hdr.payload_size > 0) {
    in.read(reinterpret_cast<char*>(payload.data()),
            static_cast<std::streamsize>(hdr.payload_size));
    if (!in) {
      throw std::runtime_error(
          "lesson_index: snapshot payload truncated: " + path.string());
    }
  }
  std::uint32_t actual_crc = crc32c(payload.data(), payload.size());
  if (actual_crc != hdr.crc32c_payload) {
    throw std::runtime_error(
        "lesson_index: snapshot CRC mismatch — file is corrupt: " +
        path.string());
  }
  return payload;
}

template <typename T>
void append_pod_(std::vector<std::uint8_t>& buf, const T& value) {
  const auto* p = reinterpret_cast<const std::uint8_t*>(&value);
  buf.insert(buf.end(), p, p + sizeof(T));
}

template <typename T>
T read_pod_(const std::uint8_t*& cursor, const std::uint8_t* end) {
  if (cursor + sizeof(T) > end) {
    throw std::runtime_error("lesson_index: snapshot payload truncated");
  }
  T value{};
  std::memcpy(&value, cursor, sizeof(T));
  cursor += sizeof(T);
  return value;
}

void append_string_(std::vector<std::uint8_t>& buf, std::string_view s) {
  append_pod_(buf, static_cast<std::uint32_t>(s.size()));
  buf.insert(buf.end(), s.begin(), s.end());
}

std::string read_string_(const std::uint8_t*& cursor, const std::uint8_t* end) {
  auto len = read_pod_<std::uint32_t>(cursor, end);
  if (cursor + len > end) {
    throw std::runtime_error("lesson_index: string length overruns payload");
  }
  std::string out(reinterpret_cast<const char*>(cursor), len);
  cursor += len;
  return out;
}

}  // namespace

// ── ScopedLessonIndex impl ────────────────────────────────────────
struct ScopedLessonIndex::Impl {
  // path -> list of records. std::map for prefix-walk via lower_bound.
  // Future: replace with Adaptive Radix Tree per Leis 2013.
  std::map<std::string, std::vector<LessonRecord>> data;
  std::unordered_map<std::uint64_t, std::string> id_to_path;
  std::size_t max_entries;
  mutable std::shared_mutex mtx;
  mutable std::atomic<std::int64_t> last_accessed_ns;

  Impl(std::size_t cap)
      : max_entries(cap), last_accessed_ns(now_unix_ns_()) {}

  void touch() const noexcept {
    last_accessed_ns.store(now_unix_ns_(), std::memory_order_relaxed);
  }

  std::size_t total_entries() const {
    std::size_t n = 0;
    for (const auto& [_, v] : data) n += v.size();
    return n;
  }
};

ScopedLessonIndex::ScopedLessonIndex(std::size_t max_entries)
    : impl_(std::make_unique<Impl>(max_entries)) {}
ScopedLessonIndex::~ScopedLessonIndex() = default;

bool ScopedLessonIndex::add(std::string_view path, LessonRecord rec) {
  std::unique_lock lock(impl_->mtx);
  impl_->touch();
  if (impl_->total_entries() >= impl_->max_entries) return false;
  std::string key(path);
  impl_->data[key].push_back(rec);
  impl_->id_to_path[rec.autoissue_id] = key;
  return true;
}

bool ScopedLessonIndex::remove(std::uint64_t autoissue_id) {
  std::unique_lock lock(impl_->mtx);
  impl_->touch();
  auto it = impl_->id_to_path.find(autoissue_id);
  if (it == impl_->id_to_path.end()) return false;
  auto& bucket = impl_->data[it->second];
  bucket.erase(std::remove_if(bucket.begin(), bucket.end(),
                              [&](const LessonRecord& r) {
                                return r.autoissue_id == autoissue_id;
                              }),
               bucket.end());
  if (bucket.empty()) impl_->data.erase(it->second);
  impl_->id_to_path.erase(it);
  return true;
}

std::vector<LessonRecord> ScopedLessonIndex::find_by_path(
    std::string_view path, std::size_t limit) const {
  std::shared_lock lock(impl_->mtx);
  impl_->touch();
  std::string prefix(path);
  std::vector<LessonRecord> out;
  auto it = impl_->data.lower_bound(prefix);
  while (it != impl_->data.end()) {
    const auto& key = it->first;
    if (prefix.size() > key.size() || key.compare(0, prefix.size(), prefix) != 0) {
      break;
    }
    for (const auto& rec : it->second) out.push_back(rec);
    ++it;
  }
  std::sort(out.begin(), out.end(),
            [](const LessonRecord& a, const LessonRecord& b) {
              if (a.severity != b.severity) return a.severity > b.severity;
              return a.resolved_at_unix > b.resolved_at_unix;
            });
  if (out.size() > limit) out.resize(limit);
  return out;
}

void ScopedLessonIndex::save(const std::filesystem::path& p) const {
  std::shared_lock lock(impl_->mtx);
  std::vector<std::uint8_t> payload;
  append_pod_(payload, static_cast<std::uint64_t>(impl_->data.size()));
  for (const auto& [path_, recs] : impl_->data) {
    append_string_(payload, path_);
    append_pod_(payload, static_cast<std::uint32_t>(recs.size()));
    for (const auto& r : recs) {
      append_pod_(payload, r.autoissue_id);
      append_pod_(payload, r.lesson_hash);
      append_pod_(payload, r.severity);
      append_pod_(payload, r.resolved_at_unix);
    }
  }
  write_snapshot_(p, payload);
}

void ScopedLessonIndex::load(const std::filesystem::path& p) {
  auto payload = read_snapshot_(p);
  std::unique_lock lock(impl_->mtx);
  impl_->data.clear();
  impl_->id_to_path.clear();
  const std::uint8_t* cursor = payload.data();
  const std::uint8_t* end = payload.data() + payload.size();
  auto n_paths = read_pod_<std::uint64_t>(cursor, end);
  for (std::uint64_t i = 0; i < n_paths; ++i) {
    std::string path_ = read_string_(cursor, end);
    auto n_recs = read_pod_<std::uint32_t>(cursor, end);
    auto& bucket = impl_->data[path_];
    bucket.reserve(n_recs);
    for (std::uint32_t j = 0; j < n_recs; ++j) {
      LessonRecord r{};
      r.autoissue_id = read_pod_<std::uint64_t>(cursor, end);
      r.lesson_hash = read_pod_<std::uint64_t>(cursor, end);
      r.severity = read_pod_<std::uint8_t>(cursor, end);
      r.resolved_at_unix = read_pod_<std::int64_t>(cursor, end);
      bucket.push_back(r);
      impl_->id_to_path[r.autoissue_id] = path_;
    }
  }
  impl_->touch();
}

std::size_t ScopedLessonIndex::size() const noexcept {
  std::shared_lock lock(impl_->mtx);
  return impl_->total_entries();
}

std::size_t ScopedLessonIndex::memory_bytes() const noexcept {
  std::shared_lock lock(impl_->mtx);
  std::size_t total = sizeof(Impl);
  for (const auto& [k, v] : impl_->data) {
    total += k.size() + v.size() * sizeof(LessonRecord) + 32;
  }
  total += impl_->id_to_path.size() * (sizeof(std::uint64_t) + 64);
  return total;
}

void ScopedLessonIndex::reclaim_now() noexcept {
  std::unique_lock lock(impl_->mtx);
  impl_->data.clear();
  impl_->id_to_path.clear();
}

void ScopedLessonIndex::clear() noexcept { reclaim_now(); }

// ── PerfBaselineCache impl ────────────────────────────────────────
struct PerfBaselineCache::Impl {
  std::unordered_map<std::string, BaselineRecord> data;
  std::size_t max_entries;
  mutable std::shared_mutex mtx;
  mutable std::atomic<std::int64_t> last_accessed_ns;

  Impl(std::size_t cap)
      : max_entries(cap), last_accessed_ns(now_unix_ns_()) {}
};

PerfBaselineCache::PerfBaselineCache(std::size_t max_entries)
    : impl_(std::make_unique<Impl>(max_entries)) {}
PerfBaselineCache::~PerfBaselineCache() = default;

std::optional<BaselineRecord> PerfBaselineCache::get(
    std::string_view fn_sig) const {
  std::shared_lock lock(impl_->mtx);
  auto it = impl_->data.find(std::string(fn_sig));
  if (it == impl_->data.end()) return std::nullopt;
  return it->second;
}

bool PerfBaselineCache::put(std::string_view fn_sig, BaselineRecord rec) {
  std::unique_lock lock(impl_->mtx);
  if (impl_->data.size() >= impl_->max_entries &&
      impl_->data.find(std::string(fn_sig)) == impl_->data.end()) {
    return false;
  }
  impl_->data[std::string(fn_sig)] = rec;
  return true;
}

bool PerfBaselineCache::erase(std::string_view fn_sig) {
  std::unique_lock lock(impl_->mtx);
  return impl_->data.erase(std::string(fn_sig)) > 0;
}

void PerfBaselineCache::save(const std::filesystem::path& p) const {
  std::shared_lock lock(impl_->mtx);
  std::vector<std::uint8_t> payload;
  append_pod_(payload, static_cast<std::uint64_t>(impl_->data.size()));
  for (const auto& [k, v] : impl_->data) {
    append_string_(payload, k);
    append_pod_(payload, v);
  }
  write_snapshot_(p, payload);
}

void PerfBaselineCache::load(const std::filesystem::path& p) {
  auto payload = read_snapshot_(p);
  std::unique_lock lock(impl_->mtx);
  impl_->data.clear();
  const std::uint8_t* cursor = payload.data();
  const std::uint8_t* end = payload.data() + payload.size();
  auto n = read_pod_<std::uint64_t>(cursor, end);
  for (std::uint64_t i = 0; i < n; ++i) {
    std::string k = read_string_(cursor, end);
    auto v = read_pod_<BaselineRecord>(cursor, end);
    impl_->data[k] = v;
  }
}

std::size_t PerfBaselineCache::size() const noexcept {
  std::shared_lock lock(impl_->mtx);
  return impl_->data.size();
}

std::size_t PerfBaselineCache::memory_bytes() const noexcept {
  std::shared_lock lock(impl_->mtx);
  std::size_t total = sizeof(Impl);
  for (const auto& [k, _] : impl_->data) {
    total += k.size() + sizeof(BaselineRecord) + 32;
  }
  return total;
}

void PerfBaselineCache::reclaim_now() noexcept {
  std::unique_lock lock(impl_->mtx);
  impl_->data.clear();
}

void PerfBaselineCache::clear() noexcept { reclaim_now(); }

// ── CitationCache impl ────────────────────────────────────────────
struct CitationCache::Impl {
  std::unordered_map<std::string, CitationRecord> data;
  std::size_t max_entries;
  mutable std::shared_mutex mtx;

  Impl(std::size_t cap) : max_entries(cap) {}
};

CitationCache::CitationCache(std::size_t max_entries)
    : impl_(std::make_unique<Impl>(max_entries)) {}
CitationCache::~CitationCache() = default;

std::optional<CitationRecord> CitationCache::get(std::string_view key) const {
  std::shared_lock lock(impl_->mtx);
  auto it = impl_->data.find(std::string(key));
  if (it == impl_->data.end()) return std::nullopt;
  return it->second;
}

bool CitationCache::put(std::string_view key, CitationRecord rec) {
  std::unique_lock lock(impl_->mtx);
  if (impl_->data.size() >= impl_->max_entries &&
      impl_->data.find(std::string(key)) == impl_->data.end()) {
    return false;
  }
  impl_->data[std::string(key)] = rec;
  return true;
}

bool CitationCache::erase(std::string_view key) {
  std::unique_lock lock(impl_->mtx);
  return impl_->data.erase(std::string(key)) > 0;
}

void CitationCache::save(const std::filesystem::path& p) const {
  std::shared_lock lock(impl_->mtx);
  std::vector<std::uint8_t> payload;
  append_pod_(payload, static_cast<std::uint64_t>(impl_->data.size()));
  for (const auto& [k, v] : impl_->data) {
    append_string_(payload, k);
    append_pod_(payload, v);
  }
  write_snapshot_(p, payload);
}

void CitationCache::load(const std::filesystem::path& p) {
  auto payload = read_snapshot_(p);
  std::unique_lock lock(impl_->mtx);
  impl_->data.clear();
  const std::uint8_t* cursor = payload.data();
  const std::uint8_t* end = payload.data() + payload.size();
  auto n = read_pod_<std::uint64_t>(cursor, end);
  for (std::uint64_t i = 0; i < n; ++i) {
    std::string k = read_string_(cursor, end);
    auto v = read_pod_<CitationRecord>(cursor, end);
    impl_->data[k] = v;
  }
}

std::size_t CitationCache::size() const noexcept {
  std::shared_lock lock(impl_->mtx);
  return impl_->data.size();
}

std::size_t CitationCache::memory_bytes() const noexcept {
  std::shared_lock lock(impl_->mtx);
  std::size_t total = sizeof(Impl);
  for (const auto& [k, _] : impl_->data) {
    total += k.size() + sizeof(CitationRecord) + 32;
  }
  return total;
}

void CitationCache::reclaim_now() noexcept {
  std::unique_lock lock(impl_->mtx);
  impl_->data.clear();
}

void CitationCache::clear() noexcept { reclaim_now(); }

// ── Module-level API ──────────────────────────────────────────────
std::size_t memory_bytes_total() { return 0; /* per-instance only in scaffold */ }
void reclaim_all() { /* per-instance reclaim_now() is the entry point */ }
std::size_t memory_cap_bytes() noexcept { return kMemoryCapBytes; }

}  // namespace xf::lesson_index

#ifndef XF_BENCH_MODE
PYBIND11_MODULE(lesson_index, m) {
  using namespace xf::lesson_index;
  m.doc() =
      "Three-sub-index in-process cache for the new ABSOLUTE rules (A-F).\n"
      "Sources: Leis 2013 (ART), Pagh-Rodler 2001 (Cuckoo), "
      "Celis-Larson-Munro 1985 (Robin Hood), RFC 3309 (CRC-32C).";

  py::class_<LessonRecord>(m, "LessonRecord")
      .def(py::init<>())
      .def_readwrite("autoissue_id", &LessonRecord::autoissue_id)
      .def_readwrite("lesson_hash", &LessonRecord::lesson_hash)
      .def_readwrite("severity", &LessonRecord::severity)
      .def_readwrite("resolved_at_unix", &LessonRecord::resolved_at_unix);

  py::class_<BaselineRecord>(m, "BaselineRecord")
      .def(py::init<>())
      .def_readwrite("p50_ns", &BaselineRecord::p50_ns)
      .def_readwrite("p95_ns", &BaselineRecord::p95_ns)
      .def_readwrite("p99_ns", &BaselineRecord::p99_ns)
      .def_readwrite("mean_ns", &BaselineRecord::mean_ns)
      .def_readwrite("samples", &BaselineRecord::samples)
      .def_readwrite("measured_at_unix", &BaselineRecord::measured_at_unix);

  py::class_<ScopedLessonIndex>(m, "ScopedLessonIndex")
      .def(py::init<std::size_t>(),
           py::arg("max_entries") = ScopedLessonIndex::kDefaultMaxEntries)
      .def("add", &ScopedLessonIndex::add, py::arg("path"), py::arg("record"))
      .def("remove", &ScopedLessonIndex::remove, py::arg("autoissue_id"))
      .def("find_by_path", &ScopedLessonIndex::find_by_path, py::arg("path"),
           py::arg("limit") = 5)
      .def("size", &ScopedLessonIndex::size)
      .def("memory_bytes", &ScopedLessonIndex::memory_bytes)
      .def("reclaim_now", &ScopedLessonIndex::reclaim_now)
      .def("clear", &ScopedLessonIndex::clear)
      .def("save",
           [](const ScopedLessonIndex& self, const std::string& p) {
             self.save(std::filesystem::path(p));
           },
           py::arg("path"))
      .def("load",
           [](ScopedLessonIndex& self, const std::string& p) {
             self.load(std::filesystem::path(p));
           },
           py::arg("path"));

  py::class_<PerfBaselineCache>(m, "PerfBaselineCache")
      .def(py::init<std::size_t>(),
           py::arg("max_entries") = PerfBaselineCache::kDefaultMaxEntries)
      .def("get", &PerfBaselineCache::get, py::arg("fn_sig"))
      .def("put", &PerfBaselineCache::put, py::arg("fn_sig"), py::arg("record"))
      .def("erase", &PerfBaselineCache::erase, py::arg("fn_sig"))
      .def("size", &PerfBaselineCache::size)
      .def("memory_bytes", &PerfBaselineCache::memory_bytes)
      .def("reclaim_now", &PerfBaselineCache::reclaim_now)
      .def("clear", &PerfBaselineCache::clear)
      .def("save",
           [](const PerfBaselineCache& self, const std::string& p) {
             self.save(std::filesystem::path(p));
           },
           py::arg("path"))
      .def("load",
           [](PerfBaselineCache& self, const std::string& p) {
             self.load(std::filesystem::path(p));
           },
           py::arg("path"));

  py::class_<CitationCache>(m, "CitationCache")
      .def(py::init<std::size_t>(),
           py::arg("max_entries") = CitationCache::kDefaultMaxEntries)
      .def("size", &CitationCache::size)
      .def("memory_bytes", &CitationCache::memory_bytes)
      .def("reclaim_now", &CitationCache::reclaim_now)
      .def("clear", &CitationCache::clear);

  m.def("memory_cap_bytes", &memory_cap_bytes);
  m.def("memory_bytes_total", &memory_bytes_total);
  m.def("reclaim_all", &reclaim_all);
  m.def("crc32c", [](const std::string& s) {
    return crc32c(reinterpret_cast<const std::uint8_t*>(s.data()), s.size());
  });
}
#endif
