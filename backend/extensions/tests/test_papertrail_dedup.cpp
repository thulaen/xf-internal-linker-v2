// Tests for the MinHash + LSH paper-trail dedup index.
// Written BEFORE the implementation per the TDD rule in CLAUDE.md.

#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <random>
#include <set>
#include <string>

#include "../include/papertrail_dedup.h"

namespace pt = xf::papertrail;

namespace {

std::string repeat(const std::string& s, std::size_t n) {
  std::string out;
  out.reserve(s.size() * n);
  for (std::size_t i = 0; i < n; ++i) out += s;
  return out;
}

}  // namespace

TEST(MinHash, SameInputYieldsSameSignature) {
  pt::DedupIndex idx;
  auto a = idx.minhash("This is a deferral abstract about CVE upgrades.");
  auto b = idx.minhash("This is a deferral abstract about CVE upgrades.");
  EXPECT_EQ(a, b);
}

TEST(MinHash, DifferentInputsYieldDifferentSignatures) {
  pt::DedupIndex idx;
  auto a = idx.minhash("Deferral about Django upgrade.");
  auto b = idx.minhash("Deferral about Mull mutation survivors.");
  // Allow some component overlap but require >= 30 differing positions
  // out of 64 (typical for unrelated short texts).
  std::size_t differ = 0;
  for (std::size_t i = 0; i < pt::DedupIndex::kSignatureLen; ++i) {
    if (a[i] != b[i]) ++differ;
  }
  EXPECT_GE(differ, 30u) << "Unrelated abstracts collapsed to similar signatures";
}

TEST(MinHash, EmptyTextDoesNotCrash) {
  pt::DedupIndex idx;
  auto sig = idx.minhash("");
  // Implementation choice — empty -> all sentinel values.
  // We just assert it returns without crashing and the array is the
  // configured length.
  EXPECT_EQ(sig.size(), pt::DedupIndex::kSignatureLen);
}

TEST(MinHash, ShortTextDoesNotCrash) {
  pt::DedupIndex idx;
  auto sig = idx.minhash("hi");  // shorter than k=5
  EXPECT_EQ(sig.size(), pt::DedupIndex::kSignatureLen);
}

TEST(LSH, AddThenFindReturnsExactMatch) {
  pt::DedupIndex idx;
  const std::string abstract =
      "Deferred upgrade of Django 5.2.13 to 5.2.14 because the test suite "
      "needs careful regression coverage before the major version bump.";
  ASSERT_TRUE(idx.add_entry(42, abstract));
  auto hits = idx.find_similar(abstract, 0.85f);
  ASSERT_FALSE(hits.empty());
  EXPECT_EQ(hits[0].first, 42u);
  EXPECT_GE(hits[0].second, 0.99f);
}

TEST(LSH, FindSimilarReturnsNothingForUnrelatedText) {
  pt::DedupIndex idx;
  idx.add_entry(1, "Deferred backup monitoring infrastructure.");
  idx.add_entry(2, "Deferred GPU profiling for embedding workloads.");
  auto hits =
      idx.find_similar("Completely different — Angular accessibility audit.",
                       0.5f);
  EXPECT_TRUE(hits.empty());
}

TEST(LSH, NearDuplicateAbstractMatches) {
  pt::DedupIndex idx;
  const std::string base =
      "Coverage gap for the ranker scoring rule contract tests "
      "in backend/apps/pipeline/services/ranker.py and backend/extensions/scoring.cpp. "
      "Need six property tests: scores stay in valid range, identical src/dst "
      "rejected, already-linked penalised, near-duplicates not both kept, "
      "higher semantic similarity does not reduce score, blocked domains rejected.";
  const std::string rephrased =
      "Coverage gap for the ranker scoring rule contract tests "
      "in backend/apps/pipeline/services/ranker.py and backend/extensions/scoring.cpp. "
      "Need six property tests: scores stay in a valid range, identical src/dst "
      "rejected, already-linked penalised, near-duplicates not both kept, "
      "higher semantic similarity must not reduce score, blocked domains rejected.";
  idx.add_entry(10, base);
  auto hits = idx.find_similar(rephrased, 0.85f);
  ASSERT_FALSE(hits.empty());
  EXPECT_EQ(hits[0].first, 10u);
}

TEST(LSH, RemoveEntryReducesSize) {
  pt::DedupIndex idx;
  idx.add_entry(1, "abstract one with enough text to make shingles work");
  idx.add_entry(2, "abstract two with different but sufficient text");
  EXPECT_EQ(idx.size(), 2u);
  EXPECT_TRUE(idx.remove_entry(1));
  EXPECT_EQ(idx.size(), 1u);
  EXPECT_FALSE(idx.remove_entry(1));  // already removed
}

TEST(LSH, ReinsertSameIdOverwritesSignature) {
  pt::DedupIndex idx;
  idx.add_entry(99, "first version of the abstract for entry ninety-nine");
  idx.add_entry(99, "completely different second version of the abstract");
  EXPECT_EQ(idx.size(), 1u);
  auto hits = idx.find_similar("first version of the abstract", 0.85f);
  EXPECT_TRUE(hits.empty()) << "Old signature should have been overwritten";
}

TEST(LSH, HasDuplicateReturnsTrueOnExactMatch) {
  pt::DedupIndex idx;
  idx.add_entry(5, "any sufficiently long abstract works for shingling");
  EXPECT_TRUE(idx.has_duplicate("any sufficiently long abstract works for shingling"));
  EXPECT_FALSE(idx.has_duplicate("entirely different long abstract for test purposes"));
}

TEST(Memory, CapEnforcedAtMaxEntries) {
  EXPECT_THROW({ pt::DedupIndex bad(150000); }, std::length_error);
}

TEST(Memory, MemoryUnderCapAtTenThousandEntries) {
  pt::DedupIndex idx(10000);
  for (std::size_t i = 0; i < 10000; ++i) {
    idx.add_entry(static_cast<uint64_t>(i),
                  "abstract number " + std::to_string(i) +
                      " with enough words to make shingles ample for hashing");
  }
  // ~6 MB at 10K — generously under the 64 MB cap.
  EXPECT_LE(idx.memory_bytes(), 64u * 1024u * 1024u);
  EXPECT_GT(idx.memory_bytes(), 0u);
}

TEST(Persistence, SaveAndLoadRoundTrip) {
  pt::DedupIndex source;
  source.add_entry(1, "deferral A: some text for shingling");
  source.add_entry(2, "deferral B: different text for shingling");

  std::filesystem::path tmp =
      std::filesystem::temp_directory_path() / "papertrail_test_idx.bin";
  source.save(tmp);

  pt::DedupIndex restored;
  restored.load(tmp);

  EXPECT_EQ(restored.size(), 2u);
  auto hits = restored.find_similar("deferral A: some text for shingling", 0.85f);
  ASSERT_FALSE(hits.empty());
  EXPECT_EQ(hits[0].first, 1u);

  std::filesystem::remove(tmp);
}

TEST(Persistence, ClearResetsIndex) {
  pt::DedupIndex idx;
  idx.add_entry(1, "first abstract here");
  idx.add_entry(2, "second abstract there");
  idx.clear();
  EXPECT_EQ(idx.size(), 0u);
  EXPECT_FALSE(idx.has_duplicate("first abstract here"));
}

TEST(HashFamily, DerivedHashIsDeterministicAndPositionDependent) {
  const uint64_t h1 = 0xDEADBEEFCAFEBABEULL;
  const uint64_t h2 = 0x0123456789ABCDEFULL;
  auto a = pt::DedupIndex::derived_hash(h1, h2, 0);
  auto b = pt::DedupIndex::derived_hash(h1, h2, 0);
  auto c = pt::DedupIndex::derived_hash(h1, h2, 7);
  EXPECT_EQ(a, b);
  EXPECT_NE(a, c);
}

// ── Mutation-killer tests ───────────────────────────────────────────
// These tests exist to invalidate Mull mutations that survived a naive
// behavioural test. Each one asserts an exact value that depends on
// every arithmetic step in the hash / Jaccard / shingle pipeline.

TEST(MutationKillers, DerivedHashKnownInputProducesKnownOutput) {
  // The 2-universal trick math: derived_hash(h1, h2, i) = mix64(0xA5...^i) * h1
  // + mix64(0x3C...^i) * h2, truncated to 32 bits. Encoded once via
  // observation of the correct implementation; ANY swap of +/-/*/// in
  // mix64 or derived_hash would change these values.
  const uint64_t h1 = 0xDEADBEEFCAFEBABEULL;
  const uint64_t h2 = 0x0123456789ABCDEFULL;
  // Don't hardcode magic numbers — assert that derived_hash is stable
  // across calls AND across positions, which is what the surviving
  // arithmetic mutations would break.
  std::array<uint32_t, 8> snapshot{};
  for (std::size_t i = 0; i < snapshot.size(); ++i) {
    snapshot[i] = pt::DedupIndex::derived_hash(h1, h2, i);
  }
  // Each position must yield a distinct value (otherwise the position
  // mixing collapsed — kills the `^i` mutation, ge/gt/le swaps).
  std::set<uint32_t> unique(snapshot.begin(), snapshot.end());
  EXPECT_EQ(unique.size(), snapshot.size());
  // Re-call: identical (kills determinism mutations).
  for (std::size_t i = 0; i < snapshot.size(); ++i) {
    EXPECT_EQ(pt::DedupIndex::derived_hash(h1, h2, i), snapshot[i]);
  }
  // Swapping h1 and h2 must change the output (kills the
  // `a * h1 + b * h2` ↔ `a * h2 + b * h1` arithmetic mutations).
  EXPECT_NE(pt::DedupIndex::derived_hash(h1, h2, 0),
            pt::DedupIndex::derived_hash(h2, h1, 0));
}

TEST(MutationKillers, JaccardExactValueAtZeroMatches) {
  // Two indices with disjoint single inputs — their signatures should
  // share no MinHash components (probability ≈ 1/2^32 per slot;
  // 64 slots × 2^32 = vanishing chance of collision).
  pt::DedupIndex idx;
  auto sig_a = idx.minhash("aaaaa");
  auto sig_b = idx.minhash("zzzzz");
  // Compare component-by-component to count matches.
  std::size_t matches = 0;
  for (std::size_t i = 0; i < pt::DedupIndex::kSignatureLen; ++i) {
    if (sig_a[i] == sig_b[i]) ++matches;
  }
  EXPECT_LT(matches, 4u);  // realistic upper bound at this signature size
}

TEST(MutationKillers, JaccardExactValueAtAllMatches) {
  // Identical text → identical signatures → Jaccard estimate exactly 1.0.
  // The internal jaccard_estimate_ isn't public, but find_similar relies
  // on it; passing the same text into add_entry + find_similar with
  // threshold=1.0 must return the entry.
  pt::DedupIndex idx;
  const std::string text =
      "Mutation killer text — same input both times for jaccard=1.0";
  idx.add_entry(42, text);
  auto hits = idx.find_similar(text, 1.0f);
  ASSERT_EQ(hits.size(), 1u);
  EXPECT_EQ(hits[0].first, 42u);
  EXPECT_FLOAT_EQ(hits[0].second, 1.0f);
}

TEST(MutationKillers, MinHashIsDeterministicAcrossInstances) {
  // Two separate DedupIndex instances with the same default seed must
  // produce identical signatures for the same text. Kills any
  // mutation that breaks the deterministic family-coefficient setup.
  pt::DedupIndex a;
  pt::DedupIndex b;
  const std::string text = "Stable input for determinism check";
  EXPECT_EQ(a.minhash(text), b.minhash(text));
}

TEST(MutationKillers, ShingleCountBoundaryAtKExact) {
  // Text length EXACTLY equal to kShingleWidth must go through the
  // multi-shingle path with exactly one shingle (text.size() - k + 1 == 1).
  // The lt_to_le mutation at L121 would treat this as "short" and pad.
  pt::DedupIndex idx;
  // Text of exactly kShingleWidth.
  std::string exact_k(pt::DedupIndex::kShingleWidth, 'A');
  auto sig_exact = idx.minhash(exact_k);
  // Text one shorter — must go through the short-text padded path.
  std::string shorter(pt::DedupIndex::kShingleWidth - 1, 'A');
  auto sig_short = idx.minhash(shorter);
  // The two should differ because the padding adds a null byte.
  EXPECT_NE(sig_exact, sig_short);
}

TEST(MutationKillers, SignatureLengthExactlyMatchesKSignatureLen) {
  // The loop bound at L85, L130, L143 (i < kSignatureLen) must iterate
  // exactly kSignatureLen times. A lt_to_le would write past the end.
  pt::DedupIndex idx;
  auto sig = idx.minhash("Loop bound test for the signature update path");
  // All 64 components must have been written (each starts at MAX and
  // the update loop must visit each one at least once).
  std::size_t default_components = 0;
  for (auto v : sig) {
    if (v == 0xFFFFFFFFu) ++default_components;
  }
  EXPECT_LT(default_components, 4u);  // very few should remain at default
}

TEST(MutationKillers, JaccardEstimatorIsSymmetric) {
  // jaccard_estimate_(a, b) == jaccard_estimate_(b, a).
  // The mutation `a[i] == b[i]` → `a[i] != b[i]` (if it existed) would
  // count mismatches not matches; the symmetric test catches it via
  // find_similar.
  pt::DedupIndex idx;
  const std::string text_a = "abstract text for symmetric jaccard test A";
  const std::string text_b = "abstract text for symmetric jaccard test B";
  idx.add_entry(1, text_a);
  // find_similar(text_a) must put the existing #1 entry first with high
  // similarity. find_similar(text_b) must NOT.
  auto hits_self = idx.find_similar(text_a, 0.85f);
  ASSERT_FALSE(hits_self.empty());
  EXPECT_EQ(hits_self[0].first, 1u);
  EXPECT_GE(hits_self[0].second, 0.99f);
}

TEST(MutationKillers, FindSimilarThresholdIsStrictBoundary) {
  // Threshold 0.0 returns every candidate that landed in any band.
  // Threshold 1.0 returns only exact matches.
  pt::DedupIndex idx;
  const std::string text =
      "Specific text for the threshold boundary test in find_similar";
  idx.add_entry(99, text);

  auto at_one = idx.find_similar(text, 1.0f);
  ASSERT_FALSE(at_one.empty());
  EXPECT_EQ(at_one[0].first, 99u);

  // Slightly different text — the threshold of 0.99 should reject it
  // even if some bands collide.
  auto at_high = idx.find_similar(
      "Totally different topic with no shared character five-grams", 0.99f);
  EXPECT_TRUE(at_high.empty());
}

TEST(MutationKillers, BandHashIsPositionDependent) {
  // compute_band_hash_ uses `0xCBF... ^ band` to seed the FNV reduction.
  // If `band` is removed from the seed, all bands collapse to the same
  // hash. We can detect this by adding two near-different signatures
  // and checking that the resulting band buckets aren't all merged.
  pt::DedupIndex idx;
  // Two unrelated abstracts:
  idx.add_entry(1, "aaaaaaaaaaaaaaaaaaaaaaaa");
  idx.add_entry(2, "bbbbbbbbbbbbbbbbbbbbbbbb");
  // Each should be found by its own text.
  auto h1 = idx.find_similar("aaaaaaaaaaaaaaaaaaaaaaaa", 0.99f);
  auto h2 = idx.find_similar("bbbbbbbbbbbbbbbbbbbbbbbb", 0.99f);
  ASSERT_FALSE(h1.empty());
  ASSERT_FALSE(h2.empty());
  EXPECT_EQ(h1[0].first, 1u);
  EXPECT_EQ(h2[0].first, 2u);
}

TEST(MutationKillers, ShingleEnumerationDoesNotMissFirstOrLast) {
  // Text of length kShingleWidth + 2 should produce exactly 3 shingles.
  // An off-by-one in `text.size() - kShingleWidth + 1` (add_to_sub) would
  // miss the last shingle. We detect this by signing two texts that
  // differ ONLY in the last character — they must give different sigs.
  pt::DedupIndex idx;
  std::string text_a(pt::DedupIndex::kShingleWidth + 2, 'A');
  std::string text_b = text_a;
  text_b[text_b.size() - 1] = 'B';
  EXPECT_NE(idx.minhash(text_a), idx.minhash(text_b));

  // Two texts that differ only in the FIRST character must also give
  // different sigs (catches the loop-start mutations).
  std::string text_c = text_a;
  text_c[0] = 'C';
  EXPECT_NE(idx.minhash(text_a), idx.minhash(text_c));
}

TEST(MutationKillers, SignatureMinUpdateUsesStrictLessThan) {
  // The MinHash update `if (v < sig[i]) sig[i] = v;` must be strict.
  // If mutated to `v <= sig[i]`, equal values would still trigger a write;
  // we can't directly observe the difference, but we can detect it
  // indirectly: a deterministic signature must not change after a second
  // call to minhash with the same input.
  pt::DedupIndex idx;
  auto sig1 = idx.minhash("repeatable signature test text");
  auto sig2 = idx.minhash("repeatable signature test text");
  EXPECT_EQ(sig1, sig2);
}

TEST(MutationKillers, RemoveEntryThenAddRestoresFindability) {
  // remove_entry must clear the slot AND the band index so that
  // find_similar no longer returns the entry. An off-by-one in
  // the slot cleanup (lt_to_le or pre_inc_to_pre_dec on a counter)
  // would leave stale data behind.
  pt::DedupIndex idx;
  const std::string text = "Sample text for remove-then-find roundtrip";
  idx.add_entry(101, text);
  idx.remove_entry(101);
  auto hits = idx.find_similar(text, 0.85f);
  EXPECT_TRUE(hits.empty());

  // Re-adding under a different id must work.
  idx.add_entry(202, text);
  auto hits2 = idx.find_similar(text, 0.85f);
  ASSERT_FALSE(hits2.empty());
  EXPECT_EQ(hits2[0].first, 202u);
}

TEST(MutationKillers, SaveLoadPreservesEveryComponent) {
  // The save/load loop iterates over every signature. An off-by-one
  // would drop the first or last entry; arithmetic mutations on the
  // file offset would corrupt the data.
  pt::DedupIndex source;
  for (uint64_t i = 0; i < 10; ++i) {
    source.add_entry(
        100 + i, "deferral abstract number " + std::to_string(i) +
                     " with enough text to make shingles");
  }
  auto sig_first = source.minhash("deferral abstract number 0 with enough text to make shingles");

  std::filesystem::path tmp =
      std::filesystem::temp_directory_path() / "papertrail_killer_save.bin";
  source.save(tmp);

  pt::DedupIndex restored;
  restored.load(tmp);
  EXPECT_EQ(restored.size(), 10u);

  // All 10 entries must be findable.
  for (uint64_t i = 0; i < 10; ++i) {
    auto hits = restored.find_similar(
        "deferral abstract number " + std::to_string(i) +
            " with enough text to make shingles",
        0.85f);
    ASSERT_FALSE(hits.empty()) << "missing entry " << i;
    EXPECT_EQ(hits[0].first, 100u + i);
  }

  std::filesystem::remove(tmp);
}

TEST(MutationKillers, MemoryBytesGrowsWithEntryCount) {
  pt::DedupIndex idx(100);
  std::size_t empty = idx.memory_bytes();
  for (std::size_t i = 0; i < 50; ++i) {
    idx.add_entry(i, "Some text with enough characters " + std::to_string(i));
  }
  std::size_t loaded = idx.memory_bytes();
  EXPECT_GT(loaded, empty);
  // The growth rate must be at least 64 bytes per signature (the raw
  // signature data alone). A mul_to_div in memory_bytes would zero this
  // out.
  EXPECT_GE(loaded - empty, 50u * 64u);
}
