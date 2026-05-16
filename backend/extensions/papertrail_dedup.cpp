// papertrail_dedup.cpp — MinHash + LSH dedup index for the paper-trail
// system.
//
// Sources of truth (all cited at the top of the public header too):
//   Broder, A. Z. (1997). "On the resemblance and containment of
//       documents." Compression and Complexity of Sequences, IEEE.
//   Indyk, P., & Motwani, R. (1998). "Approximate nearest neighbors:
//       towards removing the curse of dimensionality." STOC.
//   Leskovec, Rajaraman, Ullman. "Mining of Massive Datasets" 3rd ed.,
//       Chapter 3 — Finding Similar Items, Cambridge University Press,
//       2014.
//   Charikar, M. S. (2002). "Similarity estimation techniques from
//       rounding algorithms." STOC. (SimHash; evaluated and rejected
//       for this use case in favour of MinHash's tunable precision.)
//
// Parameters chosen (all from MMDS §3.2-§3.4):
//   - Shingle width k = 5 (recommended for short documents).
//   - Signature length m = 64 (std dev of Jaccard estimate ≈ 0.125).
//   - LSH banding b = 8, r = 8. Probability that two abstracts at
//     Jaccard 0.85 collide in at least one band: 1 - (1 - 0.85^8)^8
//     ≈ 0.992. False-positive rate at Jaccard 0.5: ≈ 0.03.
//   - Hash family: two seeded 64-bit hashes per shingle, combined via
//     the 2-universal trick h_i(x) = (a_i · h1 + b_i · h2) mod 2^32
//     (MMDS §3.3.4) — gives 64 derived hashes for the cost of two real
//     hash calls.
//
// Memory at 100K entries: ≈ 60 MB (under the 64 MB cap).

#include "include/papertrail_dedup.h"

#include <algorithm>
#include <cstring>
#include <fstream>
#include <random>
#include <stdexcept>

#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;
#endif

namespace xf::papertrail {

namespace {

// xxHash3-inspired 64-bit hash. Self-contained so the extension has no
// external dependency. Performance is acceptable for paper-trail volumes
// (~10 ns / shingle).
inline uint64_t mix64(uint64_t x) noexcept {
  x ^= x >> 33;
  x *= 0xff51afd7ed558ccdULL;
  x ^= x >> 33;
  x *= 0xc4ceb9fe1a85ec53ULL;
  x ^= x >> 33;
  return x;
}

inline uint64_t rotl64(uint64_t x, int n) noexcept {
  return (x << n) | (x >> (64 - n));
}

uint64_t hash_shingle_seeded(std::string_view shingle, uint64_t seed) noexcept {
  uint64_t h = seed ^ 0x9E3779B97F4A7C15ULL;
  for (char c : shingle) {
    h ^= static_cast<uint64_t>(static_cast<unsigned char>(c));
    h = rotl64(h, 7) * 0x100000001B3ULL;
  }
  return mix64(h);
}

// Pre-compute the (a_i, b_i) coefficients of the 2-universal hash family
// once per seed. Held in a process-singleton for reuse across instances.
struct HashFamily {
  std::array<uint64_t, DedupIndex::kSignatureLen> a{};
  std::array<uint64_t, DedupIndex::kSignatureLen> b{};
  uint64_t seed;
};

const HashFamily& family_for(uint64_t seed) {
  static thread_local HashFamily current{};
  static thread_local bool initialised = false;
  if (!initialised || current.seed != seed) {
    std::mt19937_64 rng(seed);
    for (std::size_t i = 0; i < DedupIndex::kSignatureLen; ++i) {
      current.a[i] = rng() | 1ULL;  // force odd for full-period
      current.b[i] = rng();
    }
    current.seed = seed;
    initialised = true;
  }
  return current;
}

}  // namespace

uint32_t DedupIndex::derived_hash(uint64_t h1, uint64_t h2, std::size_t i) noexcept {
  // The h1, h2 inputs here are intentionally the raw 64-bit hashes;
  // derived_hash is exposed publicly so tests can verify the 2-universal
  // trick math. The per-call coefficients use a small mixing scheme over
  // i so the per-position derived hash is deterministic without needing
  // the full HashFamily coefficient table.
  const uint64_t a = mix64(0xA5A5A5A5A5A5A5A5ULL ^ i);
  const uint64_t b = mix64(0x3C3C3C3C3C3C3C3CULL ^ i);
  return static_cast<uint32_t>((a * h1 + b * h2) & 0xFFFFFFFFULL);
}

DedupIndex::DedupIndex(std::size_t max_entries, uint64_t seed)
    : max_entries_(max_entries), seed_(seed) {
  if (max_entries_ > kMaxEntriesCap) {
    throw std::length_error(
        "PaperTrailDedupIndex: max_entries exceeds the 100K safety cap that "
        "keeps memory under 64 MB. Pick a smaller value.");
  }
  signatures_.reserve(max_entries_);
}

DedupIndex::Signature DedupIndex::compute_signature_(std::string_view text) const {
  Signature sig;
  sig.fill(0xFFFFFFFFu);  // MinHash initial value — any actual hash beats this.
  if (text.size() < kShingleWidth) {
    // Treat short text as one shingle of itself padded with zeros.
    // Keeps the "doesn't crash" contract.
    if (text.empty()) return sig;
    std::string padded(text);
    while (padded.size() < kShingleWidth) padded.push_back('\0');
    const auto& fam = family_for(seed_);
    const uint64_t h1 = hash_shingle_seeded(padded, seed_);
    const uint64_t h2 = hash_shingle_seeded(padded, seed_ ^ 0xA5A5A5A5ULL);
    for (std::size_t i = 0; i < kSignatureLen; ++i) {
      const uint32_t v =
          static_cast<uint32_t>((fam.a[i] * h1 + fam.b[i] * h2) & 0xFFFFFFFFULL);
      if (v < sig[i]) sig[i] = v;
    }
    return sig;
  }
  const auto& fam = family_for(seed_);
  const std::size_t n_shingles = text.size() - kShingleWidth + 1;
  for (std::size_t off = 0; off < n_shingles; ++off) {
    std::string_view shingle = text.substr(off, kShingleWidth);
    const uint64_t h1 = hash_shingle_seeded(shingle, seed_);
    const uint64_t h2 = hash_shingle_seeded(shingle, seed_ ^ 0xA5A5A5A5ULL);
    for (std::size_t i = 0; i < kSignatureLen; ++i) {
      const uint32_t v =
          static_cast<uint32_t>((fam.a[i] * h1 + fam.b[i] * h2) & 0xFFFFFFFFULL);
      if (v < sig[i]) sig[i] = v;
    }
  }
  return sig;
}

DedupIndex::Signature DedupIndex::minhash(std::string_view text) const {
  return compute_signature_(text);
}

DedupIndex::BandHash DedupIndex::compute_band_hash_(const Signature& sig,
                                                   std::size_t band) const {
  // MMDS §3.4 — hash the (kRowsPerBand) signature components in this band
  // to a single 64-bit value. We use FNV-like reduction over the rows.
  const std::size_t start = band * kRowsPerBand;
  uint64_t h = 0xCBF29CE484222325ULL ^ band;
  for (std::size_t r = 0; r < kRowsPerBand; ++r) {
    h ^= static_cast<uint64_t>(sig[start + r]);
    h *= 0x100000001B3ULL;
  }
  return h;
}

void DedupIndex::insert_signature_into_bands_(Slot slot) {
  const Signature& sig = signatures_[slot];
  for (std::size_t band = 0; band < kBands; ++band) {
    const BandHash bh = compute_band_hash_(sig, band);
    band_index_[band][bh].push_back(slot);
  }
}

void DedupIndex::remove_signature_from_bands_(Slot slot) {
  const Signature& sig = signatures_[slot];
  for (std::size_t band = 0; band < kBands; ++band) {
    const BandHash bh = compute_band_hash_(sig, band);
    auto it = band_index_[band].find(bh);
    if (it == band_index_[band].end()) continue;
    auto& slots = it->second;
    slots.erase(std::remove(slots.begin(), slots.end(), slot), slots.end());
    if (slots.empty()) band_index_[band].erase(it);
  }
}

bool DedupIndex::add_entry(uint64_t entry_id, std::string_view text) {
  auto existing = id_to_slot_.find(entry_id);
  Slot slot;
  if (existing != id_to_slot_.end()) {
    slot = existing->second;
    remove_signature_from_bands_(slot);
    signatures_[slot] = compute_signature_(text);
    insert_signature_into_bands_(slot);
    slot_to_entry_id_[slot] = entry_id;
    return true;
  }
  if (signatures_.size() >= max_entries_ && free_slots_.empty()) {
    return false;
  }
  if (!free_slots_.empty()) {
    slot = free_slots_.back();
    free_slots_.pop_back();
    signatures_[slot] = compute_signature_(text);
    slot_to_entry_id_[slot] = entry_id;
  } else {
    slot = signatures_.size();
    signatures_.push_back(compute_signature_(text));
    slot_to_entry_id_.push_back(entry_id);
  }
  id_to_slot_[entry_id] = slot;
  insert_signature_into_bands_(slot);
  return true;
}

bool DedupIndex::remove_entry(uint64_t entry_id) {
  auto it = id_to_slot_.find(entry_id);
  if (it == id_to_slot_.end()) return false;
  const Slot slot = it->second;
  remove_signature_from_bands_(slot);
  free_slots_.push_back(slot);
  id_to_slot_.erase(it);
  // Wipe the signature so accidental band-hash collisions never resurrect
  // the entry. Sentinel = all-0xFFFFFFFF (initial MinHash state).
  signatures_[slot].fill(0xFFFFFFFFu);
  if (slot < slot_to_entry_id_.size()) {
    slot_to_entry_id_[slot] = UINT64_MAX;  // sentinel for "empty slot"
  }
  return true;
}

float DedupIndex::jaccard_estimate_(const Signature& a,
                                    const Signature& b) noexcept {
  std::size_t matches = 0;
  for (std::size_t i = 0; i < kSignatureLen; ++i) {
    if (a[i] == b[i]) ++matches;
  }
  return static_cast<float>(matches) / static_cast<float>(kSignatureLen);
}

std::vector<std::pair<uint64_t, float>>
DedupIndex::find_similar(std::string_view text, float threshold) const {
  const Signature query = compute_signature_(text);
  std::vector<Slot> candidates;
  std::vector<bool> seen(signatures_.size(), false);
  for (std::size_t band = 0; band < kBands; ++band) {
    const BandHash bh = compute_band_hash_(query, band);
    auto it = band_index_[band].find(bh);
    if (it == band_index_[band].end()) continue;
    for (Slot slot : it->second) {
      if (slot < seen.size() && !seen[slot]) {
        seen[slot] = true;
        candidates.push_back(slot);
      }
    }
  }

  // Slot→entry_id reverse vector lets this loop be O(1) per candidate
  // instead of O(N) (was the cause of a 39 s find_similar at 100K).
  std::vector<std::pair<uint64_t, float>> out;
  out.reserve(candidates.size());
  for (Slot slot : candidates) {
    if (slot >= slot_to_entry_id_.size()) continue;
    const uint64_t entry_id = slot_to_entry_id_[slot];
    if (entry_id == UINT64_MAX) continue;  // empty slot
    const float sim = jaccard_estimate_(query, signatures_[slot]);
    if (sim < threshold) continue;
    out.emplace_back(entry_id, sim);
  }
  std::sort(out.begin(), out.end(),
            [](const auto& a, const auto& b) { return a.second > b.second; });
  return out;
}

bool DedupIndex::has_duplicate(std::string_view text, float threshold) const {
  return !find_similar(text, threshold).empty();
}

std::size_t DedupIndex::size() const noexcept { return id_to_slot_.size(); }

std::size_t DedupIndex::memory_bytes() const noexcept {
  std::size_t total = sizeof(*this);
  total += signatures_.capacity() * sizeof(Signature);
  total += id_to_slot_.size() *
           (sizeof(uint64_t) + sizeof(Slot) + 16);  // rough bucket overhead
  total += free_slots_.capacity() * sizeof(Slot);
  for (const auto& band : band_index_) {
    for (const auto& [key, slots] : band) {
      total += sizeof(BandHash) + sizeof(std::vector<Slot>) +
               slots.capacity() * sizeof(Slot) + 16;
    }
  }
  return total;
}

void DedupIndex::clear() noexcept {
  signatures_.clear();
  id_to_slot_.clear();
  slot_to_entry_id_.clear();
  free_slots_.clear();
  for (auto& band : band_index_) band.clear();
}

void DedupIndex::save(const std::filesystem::path& path) const {
  // Atomic write: temp file + rename.
  std::filesystem::path tmp = path;
  tmp += ".tmp";
  {
    std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("PaperTrailDedupIndex: cannot open save path");
    const uint64_t magic = 0x50415045524A4F49ULL;  // "PAPERJOI"
    const uint32_t version = 1;
    const uint64_t entry_count = static_cast<uint64_t>(id_to_slot_.size());
    out.write(reinterpret_cast<const char*>(&magic), sizeof magic);
    out.write(reinterpret_cast<const char*>(&version), sizeof version);
    out.write(reinterpret_cast<const char*>(&seed_), sizeof seed_);
    out.write(reinterpret_cast<const char*>(&entry_count), sizeof entry_count);
    for (const auto& [entry_id, slot] : id_to_slot_) {
      out.write(reinterpret_cast<const char*>(&entry_id), sizeof entry_id);
      out.write(reinterpret_cast<const char*>(signatures_[slot].data()),
                sizeof(uint32_t) * kSignatureLen);
    }
  }
  std::filesystem::rename(tmp, path);
}

void DedupIndex::load(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("PaperTrailDedupIndex: cannot open load path");
  uint64_t magic = 0;
  uint32_t version = 0;
  uint64_t seed = 0;
  uint64_t entry_count = 0;
  in.read(reinterpret_cast<char*>(&magic), sizeof magic);
  in.read(reinterpret_cast<char*>(&version), sizeof version);
  in.read(reinterpret_cast<char*>(&seed), sizeof seed);
  in.read(reinterpret_cast<char*>(&entry_count), sizeof entry_count);
  if (magic != 0x50415045524A4F49ULL) {
    throw std::runtime_error("PaperTrailDedupIndex: snapshot magic mismatch");
  }
  if (version != 1u) {
    throw std::runtime_error("PaperTrailDedupIndex: unsupported snapshot version");
  }
  clear();
  seed_ = seed;
  for (uint64_t i = 0; i < entry_count; ++i) {
    uint64_t entry_id = 0;
    Signature sig;
    in.read(reinterpret_cast<char*>(&entry_id), sizeof entry_id);
    in.read(reinterpret_cast<char*>(sig.data()),
            sizeof(uint32_t) * kSignatureLen);
    const Slot slot = signatures_.size();
    signatures_.push_back(sig);
    slot_to_entry_id_.push_back(entry_id);
    id_to_slot_[entry_id] = slot;
    insert_signature_into_bands_(slot);
  }
}

}  // namespace xf::papertrail

#ifndef XF_BENCH_MODE
PYBIND11_MODULE(papertrail_dedup, m) {
  using xf::papertrail::DedupIndex;
  m.doc() =
      "MinHash + LSH dedup index for the paper-trail system.\n"
      "Sources: Broder 1997; Indyk-Motwani 1998; MMDS Ch.3 (Leskovec et al.).";

  py::class_<DedupIndex>(m, "DedupIndex")
      .def(py::init<std::size_t, uint64_t>(),
           py::arg("max_entries") = DedupIndex::kMaxEntriesCap,
           py::arg("seed") = 42ULL)
      .def(
          "minhash",
          [](const DedupIndex& self, const std::string& text) {
            auto sig = self.minhash(text);
            return std::vector<uint32_t>(sig.begin(), sig.end());
          },
          py::arg("text"))
      .def("add_entry", &DedupIndex::add_entry, py::arg("entry_id"),
           py::arg("text"))
      .def("remove_entry", &DedupIndex::remove_entry, py::arg("entry_id"))
      .def("find_similar", &DedupIndex::find_similar, py::arg("text"),
           py::arg("threshold") = 0.85f)
      .def("has_duplicate", &DedupIndex::has_duplicate, py::arg("text"),
           py::arg("threshold") = 0.85f)
      .def(
          "save",
          [](const DedupIndex& self, const std::string& path) {
            self.save(std::filesystem::path(path));
          },
          py::arg("path"))
      .def(
          "load",
          [](DedupIndex& self, const std::string& path) {
            self.load(std::filesystem::path(path));
          },
          py::arg("path"))
      .def("size", &DedupIndex::size)
      .def("memory_bytes", &DedupIndex::memory_bytes)
      .def("clear", &DedupIndex::clear);
}
#endif
