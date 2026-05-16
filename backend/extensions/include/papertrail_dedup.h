// papertrail_dedup.h — MinHash + LSH dedup index for the paper-trail
// system. See backend/extensions/papertrail_dedup.cpp for the impl.
//
// Sources of truth:
//   Broder 1997 — "On the resemblance and containment of documents"
//   Indyk & Motwani 1998 — "Approximate nearest neighbors..."
//   Leskovec, Rajaraman, Ullman, MMDS 3rd ed. Chapter 3
//
// Memory budget at 100K entries: ≈ 60 MB (signatures + LSH band index).

#ifndef XF_PAPERTRAIL_DEDUP_H
#define XF_PAPERTRAIL_DEDUP_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace xf::papertrail {

class DedupIndex {
 public:
  static constexpr std::size_t kSignatureLen = 64;
  static constexpr std::size_t kBands = 8;
  static constexpr std::size_t kRowsPerBand = 8;
  static constexpr std::size_t kShingleWidth = 5;
  static constexpr std::size_t kMaxEntriesCap = 100000;

  using Signature = std::array<uint32_t, kSignatureLen>;

  explicit DedupIndex(std::size_t max_entries = kMaxEntriesCap,
                      uint64_t seed = 42ULL);

  // Compute MinHash signature for `text` without inserting.
  Signature minhash(std::string_view text) const;

  // Insert (entry_id, text) into the LSH band index. Returns true on
  // success, false if at capacity. Idempotent on entry_id — re-insert
  // overwrites the prior signature.
  bool add_entry(uint64_t entry_id, std::string_view text);

  // Remove entry by id. Returns true if it was present.
  bool remove_entry(uint64_t entry_id);

  // Return (entry_id, estimated_jaccard) pairs with similarity >= threshold,
  // sorted by similarity descending.
  std::vector<std::pair<uint64_t, float>> find_similar(
      std::string_view text, float threshold = 0.85f) const;

  // True iff any indexed entry has similarity >= threshold.
  bool has_duplicate(std::string_view text, float threshold = 0.85f) const;

  // Persist / restore binary snapshot. Format is private; do not edit by
  // hand. Save is atomic (tmp + rename).
  void save(const std::filesystem::path& path) const;
  void load(const std::filesystem::path& path);

  // Diagnostics.
  std::size_t size() const noexcept;
  std::size_t memory_bytes() const noexcept;
  void clear() noexcept;

  // Hash family — exposed for tests so they can verify the 2-universal
  // trick math against the textbook formula.
  static uint32_t derived_hash(uint64_t h1, uint64_t h2, std::size_t i) noexcept;

 private:
  using BandHash = uint64_t;
  using Slot = std::size_t;
  using BandIndex = std::unordered_map<BandHash, std::vector<Slot>>;

  std::size_t max_entries_;
  uint64_t seed_;
  std::vector<Signature> signatures_;
  std::unordered_map<uint64_t, Slot> id_to_slot_;
  // Reverse map so find_similar can resolve slot→entry_id in O(1) instead of
  // walking id_to_slot_ for every candidate. Uses sentinel UINT64_MAX for
  // empty slots so find_similar can skip them.
  std::vector<uint64_t> slot_to_entry_id_;
  std::vector<Slot> free_slots_;
  std::array<BandIndex, kBands> band_index_;

  // Replace internal slot helpers — implemented in the .cpp.
  Signature compute_signature_(std::string_view text) const;
  BandHash compute_band_hash_(const Signature& sig, std::size_t band) const;
  void insert_signature_into_bands_(Slot slot);
  void remove_signature_from_bands_(Slot slot);
  static float jaccard_estimate_(const Signature& a, const Signature& b) noexcept;
};

}  // namespace xf::papertrail

#endif  // XF_PAPERTRAIL_DEDUP_H
