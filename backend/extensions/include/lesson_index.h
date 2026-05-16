// lesson_index.h — three-sub-index in-process cache for the new ABSOLUTE
// rules (A-F). See backend/extensions/lesson_index.cpp for implementation
// and docs/specs/lesson-index.md for the operator-facing spec + citations.
//
// Sources of truth:
//   Leis, Kemper, Neumann 2013 — Adaptive Radix Tree (ScopedLessonIndex)
//   Pagh & Rodler 2001 — Cuckoo Hashing (PerfBaselineCache)
//   Celis, Larson, Munro 1985 — Robin Hood Hashing (CitationCache)
//   Evans 2006 — jemalloc memory accounting (mallinfo2-style)
//   RFC 3309 — CRC-32C checksum (snapshot integrity)
//
// Memory budget at typical scale: ~168 MB.
// Hard cap: 512 MB total across all three sub-indices.

#ifndef XF_LESSON_INDEX_H
#define XF_LESSON_INDEX_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace xf::lesson_index {

// ── Shared constants ──────────────────────────────────────────────
constexpr std::size_t kMemoryCapBytes = 512ULL * 1024ULL * 1024ULL;
constexpr std::uint32_t kSnapshotMagic =
    0x494C4658u;  // "XFLI" little-endian
constexpr std::uint32_t kSnapshotVersion = 1u;
constexpr std::int64_t kDefaultIdleTimeoutSeconds = 300;  // 5 min

// ── Sub-index 1: ScopedLessonIndex ────────────────────────────────
struct LessonRecord {
  std::uint64_t autoissue_id;
  std::uint64_t lesson_hash;  // SHA1-64 of the lesson text
  std::uint8_t severity;       // 0=low, 1=medium, 2=high, 3=critical
  std::int64_t resolved_at_unix;

  bool operator==(const LessonRecord& other) const noexcept {
    return autoissue_id == other.autoissue_id &&
           lesson_hash == other.lesson_hash &&
           severity == other.severity &&
           resolved_at_unix == other.resolved_at_unix;
  }
};

class ScopedLessonIndex {
 public:
  static constexpr std::size_t kDefaultMaxEntries = 1'000'000;

  explicit ScopedLessonIndex(std::size_t max_entries = kDefaultMaxEntries);
  ~ScopedLessonIndex();

  ScopedLessonIndex(const ScopedLessonIndex&) = delete;
  ScopedLessonIndex& operator=(const ScopedLessonIndex&) = delete;

  std::vector<LessonRecord> find_by_path(std::string_view path,
                                         std::size_t limit = 5) const;
  bool add(std::string_view path, LessonRecord rec);
  bool remove(std::uint64_t autoissue_id);

  void save(const std::filesystem::path& p) const;
  void load(const std::filesystem::path& p);

  std::size_t size() const noexcept;
  std::size_t memory_bytes() const noexcept;
  void reclaim_now() noexcept;
  void clear() noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

// ── Sub-index 2: PerfBaselineCache ────────────────────────────────
struct BaselineRecord {
  std::uint64_t p50_ns;
  std::uint64_t p95_ns;
  std::uint64_t p99_ns;
  std::uint64_t mean_ns;
  std::uint32_t samples;
  std::int64_t measured_at_unix;

  bool operator==(const BaselineRecord& other) const noexcept {
    return p50_ns == other.p50_ns && p95_ns == other.p95_ns &&
           p99_ns == other.p99_ns && mean_ns == other.mean_ns &&
           samples == other.samples &&
           measured_at_unix == other.measured_at_unix;
  }
};

class PerfBaselineCache {
 public:
  static constexpr std::size_t kDefaultMaxEntries = 50'000;

  explicit PerfBaselineCache(std::size_t max_entries = kDefaultMaxEntries);
  ~PerfBaselineCache();

  PerfBaselineCache(const PerfBaselineCache&) = delete;
  PerfBaselineCache& operator=(const PerfBaselineCache&) = delete;

  std::optional<BaselineRecord> get(std::string_view fn_sig) const;
  bool put(std::string_view fn_sig, BaselineRecord rec);
  bool erase(std::string_view fn_sig);

  void save(const std::filesystem::path& p) const;
  void load(const std::filesystem::path& p);

  std::size_t size() const noexcept;
  std::size_t memory_bytes() const noexcept;
  void reclaim_now() noexcept;
  void clear() noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

// ── Sub-index 3: CitationCache ────────────────────────────────────
struct CitationRecord {
  char kind;                  // 'p' patent, 'd' doi, 'r' rfc, 'u' url
  std::array<char, 128> id;
  std::array<char, 256> title;
  std::array<char, 256> authors;
  std::int16_t year;
  std::array<char, 256> url;
  std::uint8_t accessible;     // 0=unverified, 1=ok, 2=paywall, 3=dead
  std::int64_t last_checked_unix;

  bool operator==(const CitationRecord& other) const noexcept {
    return kind == other.kind && id == other.id && title == other.title &&
           authors == other.authors && year == other.year && url == other.url &&
           accessible == other.accessible &&
           last_checked_unix == other.last_checked_unix;
  }
};

class CitationCache {
 public:
  static constexpr std::size_t kDefaultMaxEntries = 10'000;

  explicit CitationCache(std::size_t max_entries = kDefaultMaxEntries);
  ~CitationCache();

  CitationCache(const CitationCache&) = delete;
  CitationCache& operator=(const CitationCache&) = delete;

  std::optional<CitationRecord> get(std::string_view key) const;
  bool put(std::string_view key, CitationRecord rec);
  bool erase(std::string_view key);

  void save(const std::filesystem::path& p) const;
  void load(const std::filesystem::path& p);

  std::size_t size() const noexcept;
  std::size_t memory_bytes() const noexcept;
  void reclaim_now() noexcept;
  void clear() noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

// ── Module-level API ──────────────────────────────────────────────
std::size_t memory_bytes_total();
void reclaim_all();
std::size_t memory_cap_bytes() noexcept;

// CRC-32C (RFC 3309) — exposed for snapshot integrity tests.
std::uint32_t crc32c(const std::uint8_t* data, std::size_t len) noexcept;

}  // namespace xf::lesson_index

#endif  // XF_LESSON_INDEX_H
