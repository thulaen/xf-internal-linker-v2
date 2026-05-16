// GTest cases for the lesson_index extension.
// TDD discipline (CLAUDE.md ABSOLUTE rule): these tests are the Red phase;
// they specify the contract BEFORE the implementation in lesson_index.cpp.

#include <gtest/gtest.h>

#include <algorithm>
#include <cstring>
#include <filesystem>
#include <string>

#include "../include/lesson_index.h"

namespace li = xf::lesson_index;

namespace {

li::LessonRecord make_lesson(std::uint64_t id, std::uint8_t sev = 2,
                             std::int64_t resolved_at = 1'700'000'000) {
  return li::LessonRecord{id, id * 31u, sev, resolved_at};
}

li::BaselineRecord make_baseline(std::uint64_t p50 = 1000) {
  return li::BaselineRecord{p50, p50 * 2, p50 * 4, p50 + p50 / 2, 1000,
                            1'700'000'000};
}

li::CitationRecord make_citation(char kind = 'd',
                                 const char* id = "10.1/example") {
  li::CitationRecord rec{};
  rec.kind = kind;
  std::strncpy(rec.id.data(), id, sizeof(rec.id) - 1);
  std::strncpy(rec.title.data(), "Sample title", sizeof(rec.title) - 1);
  std::strncpy(rec.authors.data(), "A, B, C", sizeof(rec.authors) - 1);
  rec.year = 2024;
  std::strncpy(rec.url.data(), "https://example.org/x", sizeof(rec.url) - 1);
  rec.accessible = 1;
  rec.last_checked_unix = 1'700'000'000;
  return rec;
}

}  // namespace

// ── ScopedLessonIndex ─────────────────────────────────────────────

TEST(ScopedLessonIndex, AddThenFindReturnsRecord) {
  li::ScopedLessonIndex idx;
  ASSERT_TRUE(idx.add("backend/apps/audit/error_ingest.py", make_lesson(1)));
  auto hits = idx.find_by_path("backend/apps/audit/error_ingest.py");
  ASSERT_EQ(hits.size(), 1u);
  EXPECT_EQ(hits[0].autoissue_id, 1u);
}

TEST(ScopedLessonIndex, PrefixLookupReturnsAllDescendants) {
  li::ScopedLessonIndex idx;
  idx.add("backend/apps/audit/error_ingest.py", make_lesson(1));
  idx.add("backend/apps/audit/fix_suggestions.py", make_lesson(2));
  idx.add("backend/apps/audit/services/undo.py", make_lesson(3));
  idx.add("backend/apps/auto_issues/admin.py", make_lesson(4));
  auto hits = idx.find_by_path("backend/apps/audit");
  EXPECT_EQ(hits.size(), 3u);
}

TEST(ScopedLessonIndex, SortedBySeverityDescThenRecencyDesc) {
  li::ScopedLessonIndex idx;
  idx.add("backend/apps/audit/a.py", make_lesson(1, /*sev*/ 1, 1000));
  idx.add("backend/apps/audit/b.py", make_lesson(2, /*sev*/ 3, 500));
  idx.add("backend/apps/audit/c.py", make_lesson(3, /*sev*/ 3, 2000));
  auto hits = idx.find_by_path("backend/apps/audit");
  ASSERT_EQ(hits.size(), 3u);
  EXPECT_EQ(hits[0].autoissue_id, 3u);  // sev=3, newest
  EXPECT_EQ(hits[1].autoissue_id, 2u);  // sev=3, older
  EXPECT_EQ(hits[2].autoissue_id, 1u);  // sev=1
}

TEST(ScopedLessonIndex, LimitTruncatesResults) {
  li::ScopedLessonIndex idx;
  for (std::uint64_t i = 1; i <= 10; ++i) {
    idx.add("backend/apps/audit/x.py", make_lesson(i));
  }
  auto hits = idx.find_by_path("backend/apps/audit/x.py", /*limit*/ 3);
  EXPECT_EQ(hits.size(), 3u);
}

TEST(ScopedLessonIndex, RemoveByIdEliminatesEntry) {
  li::ScopedLessonIndex idx;
  idx.add("a/b/c", make_lesson(1));
  idx.add("a/b/c", make_lesson(2));
  EXPECT_TRUE(idx.remove(1));
  auto hits = idx.find_by_path("a/b/c");
  ASSERT_EQ(hits.size(), 1u);
  EXPECT_EQ(hits[0].autoissue_id, 2u);
}

TEST(ScopedLessonIndex, EmptyPrefixReturnsAll) {
  li::ScopedLessonIndex idx;
  idx.add("a", make_lesson(1));
  idx.add("b", make_lesson(2));
  auto hits = idx.find_by_path("");
  EXPECT_EQ(hits.size(), 2u);
}

TEST(ScopedLessonIndex, MemoryStaysUnderHardCap) {
  li::ScopedLessonIndex idx(/*max_entries=*/100'000);
  for (std::uint64_t i = 0; i < 100'000; ++i) {
    idx.add("backend/apps/x/y/z.py", make_lesson(i));
  }
  EXPECT_LE(idx.memory_bytes(), 200ULL * 1024ULL * 1024ULL);
}

TEST(ScopedLessonIndex, SaveLoadRoundTripPreservesRecords) {
  li::ScopedLessonIndex source;
  source.add("backend/apps/audit/a.py", make_lesson(11, 3, 100));
  source.add("backend/apps/audit/b.py", make_lesson(22, 2, 200));

  std::filesystem::path tmp =
      std::filesystem::temp_directory_path() / "li_scoped.bin";
  source.save(tmp);

  li::ScopedLessonIndex restored;
  restored.load(tmp);
  EXPECT_EQ(restored.size(), 2u);
  auto hits = restored.find_by_path("backend/apps/audit");
  EXPECT_EQ(hits.size(), 2u);

  std::filesystem::remove(tmp);
}

TEST(ScopedLessonIndex, ClearResetsSize) {
  li::ScopedLessonIndex idx;
  idx.add("a/b/c", make_lesson(1));
  idx.add("d/e/f", make_lesson(2));
  idx.clear();
  EXPECT_EQ(idx.size(), 0u);
  EXPECT_TRUE(idx.find_by_path("a/b/c").empty());
}

// ── PerfBaselineCache ─────────────────────────────────────────────

TEST(PerfBaselineCache, PutThenGetReturnsRecord) {
  li::PerfBaselineCache cache;
  EXPECT_TRUE(cache.put("apps.pipeline.ranker", make_baseline(5000)));
  auto out = cache.get("apps.pipeline.ranker");
  ASSERT_TRUE(out.has_value());
  EXPECT_EQ(out->p50_ns, 5000u);
}

TEST(PerfBaselineCache, MissingKeyReturnsNullopt) {
  li::PerfBaselineCache cache;
  EXPECT_FALSE(cache.get("nonexistent.function").has_value());
}

TEST(PerfBaselineCache, PutOverwritesPriorRecord) {
  li::PerfBaselineCache cache;
  cache.put("k", make_baseline(1000));
  cache.put("k", make_baseline(2000));
  auto out = cache.get("k");
  ASSERT_TRUE(out.has_value());
  EXPECT_EQ(out->p50_ns, 2000u);
}

TEST(PerfBaselineCache, EraseReturnsTrueOnSuccess) {
  li::PerfBaselineCache cache;
  cache.put("k", make_baseline());
  EXPECT_TRUE(cache.erase("k"));
  EXPECT_FALSE(cache.erase("k"));
  EXPECT_FALSE(cache.get("k").has_value());
}

TEST(PerfBaselineCache, SaveLoadRoundTrip) {
  li::PerfBaselineCache source;
  source.put("a", make_baseline(100));
  source.put("b", make_baseline(200));

  std::filesystem::path tmp =
      std::filesystem::temp_directory_path() / "li_perf.bin";
  source.save(tmp);

  li::PerfBaselineCache restored;
  restored.load(tmp);
  EXPECT_EQ(restored.size(), 2u);
  EXPECT_EQ(restored.get("a")->p50_ns, 100u);
  EXPECT_EQ(restored.get("b")->p50_ns, 200u);

  std::filesystem::remove(tmp);
}

TEST(PerfBaselineCache, FillsUpToCapWithoutCrash) {
  li::PerfBaselineCache cache(/*max_entries=*/1024);
  for (std::uint64_t i = 0; i < 1024; ++i) {
    cache.put("fn_" + std::to_string(i), make_baseline(i + 1));
  }
  EXPECT_GT(cache.size(), 0u);
  EXPECT_LE(cache.memory_bytes(), 1ULL * 1024ULL * 1024ULL);
}

// ── CitationCache ─────────────────────────────────────────────────

TEST(CitationCache, PutThenGetReturnsRecord) {
  li::CitationCache cache;
  EXPECT_TRUE(cache.put("doi:10.1109/ICDE.2013.6544812",
                         make_citation('d', "10.1109/ICDE.2013.6544812")));
  auto out = cache.get("doi:10.1109/ICDE.2013.6544812");
  ASSERT_TRUE(out.has_value());
  EXPECT_EQ(out->kind, 'd');
  EXPECT_EQ(out->year, 2024);
}

TEST(CitationCache, MissingKeyReturnsNullopt) {
  li::CitationCache cache;
  EXPECT_FALSE(cache.get("doi:nope").has_value());
}

TEST(CitationCache, EraseAndReinsertWorks) {
  li::CitationCache cache;
  cache.put("k", make_citation());
  EXPECT_TRUE(cache.erase("k"));
  cache.put("k", make_citation('p', "US12345"));
  auto out = cache.get("k");
  ASSERT_TRUE(out.has_value());
  EXPECT_EQ(out->kind, 'p');
}

TEST(CitationCache, SaveLoadRoundTrip) {
  li::CitationCache source;
  source.put("a", make_citation('d', "10.1/a"));
  source.put("b", make_citation('r', "RFC3309"));

  std::filesystem::path tmp =
      std::filesystem::temp_directory_path() / "li_cite.bin";
  source.save(tmp);

  li::CitationCache restored;
  restored.load(tmp);
  EXPECT_EQ(restored.size(), 2u);
  EXPECT_EQ(restored.get("a")->kind, 'd');
  EXPECT_EQ(restored.get("b")->kind, 'r');

  std::filesystem::remove(tmp);
}

// ── Memory cap + module API ───────────────────────────────────────

TEST(Module, MemoryCapMatchesSpec) {
  EXPECT_EQ(li::memory_cap_bytes(), 512ULL * 1024ULL * 1024ULL);
}

TEST(Module, ReclaimAllRunsWithoutCrash) {
  // The bare API call must succeed even with no instances active.
  li::reclaim_all();
}

TEST(Module, MemoryBytesTotalIsNonNegative) {
  auto total = li::memory_bytes_total();
  EXPECT_LE(total, li::memory_cap_bytes());
}

// ── CRC-32C (RFC 3309) ────────────────────────────────────────────

TEST(Crc32c, KnownTestVectorFromRFC3309) {
  // RFC 3309 Appendix A — well-known test vectors.
  // "123456789" -> 0xE3069283 (Castagnoli CRC-32C).
  const std::uint8_t msg[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  EXPECT_EQ(li::crc32c(msg, sizeof msg), 0xE3069283u);
}

TEST(Crc32c, EmptyInputReturnsZero) {
  EXPECT_EQ(li::crc32c(nullptr, 0), 0u);
}

TEST(Crc32c, SingleZeroByteHasKnownValue) {
  const std::uint8_t z = 0;
  // CRC-32C of a single zero byte = 0x527D5351.
  EXPECT_EQ(li::crc32c(&z, 1), 0x527D5351u);
}

// ── Snapshot integrity ────────────────────────────────────────────

TEST(SnapshotIntegrity, CorruptedFileRejectedOnLoad) {
  li::ScopedLessonIndex source;
  source.add("a/b", make_lesson(1));
  std::filesystem::path tmp =
      std::filesystem::temp_directory_path() / "li_corrupt.bin";
  source.save(tmp);

  // Corrupt the magic.
  {
    std::FILE* f = std::fopen(tmp.string().c_str(), "rb+");
    ASSERT_NE(f, nullptr);
    char bad[4] = {'X', 'X', 'X', 'X'};
    std::fwrite(bad, 1, 4, f);
    std::fclose(f);
  }

  li::ScopedLessonIndex target;
  EXPECT_THROW(target.load(tmp), std::runtime_error);

  std::filesystem::remove(tmp);
}
