#![allow(clippy::missing_const_for_fn)]
//! Paper-trail `MinHash` + LSH near-duplicate index, ported from the C++ kernel
//! `backend/extensions/papertrail_dedup.cpp` to Rust and exposed to Python as
//! the native module `extensions.papertrail_dedup` via `PyO3`.
//!
//! A 64-component `MinHash` signature (Broder 1997) is built from 5-character
//! shingles via a 2-universal hash family (Leskovec-Rajaraman-Ullman, *Mining
//! of Massive Datasets* 3rd ed. §3.3.4). Signatures are banded 8×8 into 8
//! locality-sensitive-hashing band indexes (Indyk & Motwani 1998) so
//! `find_similar` only Jaccard-compares band-collision candidates.
//!
//! The Python-callable API matches the C++ kernel exactly — a single class
//! `DedupIndex` with the methods `minhash`, `add_entry`, `remove_entry`,
//! `find_similar`, `has_duplicate`, `save`, `load`, `size`, `memory_bytes`,
//! `clear`.
//!
//! ## Byte-identical port (snapshot round-trip)
//!
//! The whole pipeline is deterministic integer arithmetic (no `std::hash`, no
//! platform float) plus a `std::mt19937_64(seed)` for the family coefficients.
//! This port reproduces the C++ hash math exactly — `mix64`, the `rotl64`+FNV
//! shingle hash, the second base hash seeded with `seed ^ 0xA5A5A5A5`, a
//! vendored `mt19937_64` matching `std::mt19937_64` with `a_i = rng() | 1`,
//! `b_i = rng()`, and the FNV band reduction — and writes/reads the same
//! little-endian snapshot layout. An existing C++-written
//! `/app/data/papertrail.idx` therefore reloads transparently.

use std::collections::HashMap;
use std::fs;
use std::io::{self, Read, Write};
use std::path::Path;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

/// `MinHash` signature length (m). Pinned by the collision-probability math.
const SIGNATURE_LEN: usize = 64;
/// LSH band count (b).
const BANDS: usize = 8;
/// Rows per band (r). `BANDS * ROWS_PER_BAND == SIGNATURE_LEN`.
const ROWS_PER_BAND: usize = 8;
/// Shingle width (k) — characters per shingle.
const SHINGLE_WIDTH: usize = 5;
/// Hard cap on entries that keeps memory under the 64 MB budget.
const MAX_ENTRIES_CAP: usize = 100_000;
/// Snapshot magic, little-endian bytes spelling "PAPERJOI".
const SNAPSHOT_MAGIC: u64 = 0x5041_5045_524A_4F49;
/// Only snapshot version this build reads/writes.
const SNAPSHOT_VERSION: u32 = 1;
/// Sentinel `entry_id` marking a freed slot.
const EMPTY_SLOT: u64 = u64::MAX;

/// A 64-component `MinHash` signature. Each component is a `u32` `MinHash` value;
/// a never-touched component holds `0xFFFF_FFFF` (the `MinHash` initial value).
type Signature = [u32; SIGNATURE_LEN];

/// The all-`0xFFFF_FFFF` signature: the `MinHash` initial state and the wipe
/// sentinel for a freed slot.
const EMPTY_SIGNATURE: Signature = [0xFFFF_FFFF; SIGNATURE_LEN];

/// Errors the pure-Rust core can raise.
///
/// The thin `PyO3` wrapper maps these to `ValueError` / `RuntimeError`; the
/// core never references any Python type so `cargo test` links without the
/// Python runtime library.
#[derive(Debug, PartialEq, Eq)]
pub enum DedupError {
    /// `max_entries` exceeds the 100K safety cap.
    CapExceeded,
    /// The save path could not be opened/written.
    SaveOpen,
    /// The load path could not be opened/read.
    LoadOpen,
    /// The snapshot magic did not match.
    MagicMismatch,
    /// The snapshot version is not 1.
    UnsupportedVersion,
}

impl DedupError {
    /// The exact human message the C++ kernel surfaced for each error.
    #[must_use]
    pub fn message(&self) -> &'static str {
        match self {
            Self::CapExceeded => {
                "PaperTrailDedupIndex: max_entries exceeds the 100K safety cap that \
                 keeps memory under 64 MB. Pick a smaller value."
            }
            Self::SaveOpen => "PaperTrailDedupIndex: cannot open save path",
            Self::LoadOpen => "PaperTrailDedupIndex: cannot open load path",
            Self::MagicMismatch => "PaperTrailDedupIndex: snapshot magic mismatch",
            Self::UnsupportedVersion => "PaperTrailDedupIndex: unsupported snapshot version",
        }
    }
}

/// The `SplitMix64`-style finaliser used by the C++ kernel's `mix64`.
#[must_use]
fn mix64(mut x: u64) -> u64 {
    x ^= x >> 33;
    x = x.wrapping_mul(0xff51_afd7_ed55_8ccd);
    x ^= x >> 33;
    x = x.wrapping_mul(0xc4ce_b9fe_1a85_ec53);
    x ^= x >> 33;
    x
}

/// 64-bit left rotation, matching the C++ `rotl64`.
#[must_use]
fn rotl64(x: u64, n: u32) -> u64 {
    x.rotate_left(n)
}

/// Seeded shingle hash, byte-identical to the C++ `hash_shingle_seeded`: an
/// FNV-style rolling hash over the shingle bytes, finalised through `mix64`.
#[must_use]
fn hash_shingle_seeded(shingle: &[u8], seed: u64) -> u64 {
    let mut h = seed ^ 0x9E37_79B9_7F4A_7C15;
    for &c in shingle {
        h ^= u64::from(c);
        h = rotl64(h, 7).wrapping_mul(0x0000_0100_0000_01B3);
    }
    mix64(h)
}

/// Vendored 64-bit Mersenne Twister matching `std::mt19937_64(seed)` so the
/// 2-universal hash-family coefficients are byte-identical to the C++ build.
///
/// Constants are the standard MT19937-64 (Matsumoto & Nishimura): n=312, m=156,
/// the seeding multiplier `6364136223846793005`, and the
/// `B/C`/shift tempering parameters.
struct Mt19937_64 {
    state: [u64; 312],
    index: usize,
}

impl Mt19937_64 {
    const N: usize = 312;
    const M: usize = 156;
    const MATRIX_A: u64 = 0xB502_6F5A_A966_19E9;
    const UPPER_MASK: u64 = 0xFFFF_FFFF_8000_0000;
    const LOWER_MASK: u64 = 0x0000_0000_7FFF_FFFF;

    fn new(seed: u64) -> Self {
        let mut state = [0_u64; Self::N];
        state[0] = seed;
        for i in 1..Self::N {
            // C++ libstdc++ seeding recurrence for mt19937_64.
            let prev = state[i - 1];
            state[i] = (6_364_136_223_846_793_005_u64)
                .wrapping_mul(prev ^ (prev >> 62))
                .wrapping_add(i as u64);
        }
        Self {
            state,
            index: Self::N,
        }
    }

    fn generate(&mut self) {
        for i in 0..Self::N {
            let x = (self.state[i] & Self::UPPER_MASK)
                | (self.state[(i + 1) % Self::N] & Self::LOWER_MASK);
            let mut x_a = x >> 1;
            if x & 1 != 0 {
                x_a ^= Self::MATRIX_A;
            }
            self.state[i] = self.state[(i + Self::M) % Self::N] ^ x_a;
        }
        self.index = 0;
    }

    fn next_u64(&mut self) -> u64 {
        if self.index >= Self::N {
            self.generate();
        }
        let mut y = self.state[self.index];
        self.index += 1;
        // Tempering.
        y ^= (y >> 29) & 0x5555_5555_5555_5555;
        y ^= (y << 17) & 0x71D6_7FFF_EDA6_0000;
        y ^= (y << 37) & 0xFFF7_EEE0_0000_0000;
        y ^= y >> 43;
        y
    }
}

/// The 2-universal hash family: 64 `(a_i, b_i)` coefficient pairs derived once
/// per seed via the vendored `mt19937_64`, matching the C++ `family_for`.
struct HashFamily {
    a: [u64; SIGNATURE_LEN],
    b: [u64; SIGNATURE_LEN],
}

impl HashFamily {
    fn for_seed(seed: u64) -> Self {
        let mut rng = Mt19937_64::new(seed);
        let mut a = [0_u64; SIGNATURE_LEN];
        let mut b = [0_u64; SIGNATURE_LEN];
        for i in 0..SIGNATURE_LEN {
            a[i] = rng.next_u64() | 1; // force odd for full period
            b[i] = rng.next_u64();
        }
        Self { a, b }
    }
}

/// Plain-Rust `MinHash` + LSH dedup core over native types (no `PyO3`), so it is
/// unit-testable with `cargo test` without crossing the Python boundary.
///
/// Mirrors the C++ class member layout: a flat `signatures` vector indexed by
/// slot, `id_to_slot` / `slot_to_entry_id` maps, a `free_slots` reuse list, and
/// 8 LSH band indexes mapping a band hash to the colliding slots.
pub struct DedupIndexCore {
    max_entries: usize,
    seed: u64,
    family: HashFamily,
    signatures: Vec<Signature>,
    id_to_slot: HashMap<u64, usize>,
    slot_to_entry_id: Vec<u64>,
    free_slots: Vec<usize>,
    band_index: [HashMap<u64, Vec<usize>>; BANDS],
}

impl DedupIndexCore {
    /// Construct a fresh index.
    ///
    /// # Errors
    ///
    /// Returns [`DedupError::CapExceeded`] when `max_entries > 100_000`, the
    /// safety cap that keeps memory under 64 MB (the C++ kernel threw
    /// `std::length_error`, surfaced to Python as `ValueError`).
    pub fn new(max_entries: usize, seed: u64) -> Result<Self, DedupError> {
        if max_entries > MAX_ENTRIES_CAP {
            return Err(DedupError::CapExceeded);
        }
        Ok(Self {
            max_entries,
            seed,
            family: HashFamily::for_seed(seed),
            signatures: Vec::new(),
            id_to_slot: HashMap::new(),
            slot_to_entry_id: Vec::new(),
            free_slots: Vec::new(),
            band_index: std::array::from_fn(|_| HashMap::new()),
        })
    }

    /// One derived `MinHash` component: `(a_i * h1 + b_i * h2) mod 2^32`, with the
    /// `u64` multiplies/adds wrapping mod 2^64 exactly like the C++ kernel.
    #[must_use]
    fn derived(&self, i: usize, h1: u64, h2: u64) -> u32 {
        let a = self.family.a[i].wrapping_mul(h1);
        let b = self.family.b[i].wrapping_mul(h2);
        (a.wrapping_add(b) & 0xFFFF_FFFF) as u32
    }

    /// Fold one shingle's two base hashes into the running `MinHash` signature.
    fn fold_shingle(&self, sig: &mut Signature, shingle: &[u8]) {
        let h1 = hash_shingle_seeded(shingle, self.seed);
        let h2 = hash_shingle_seeded(shingle, self.seed ^ 0xA5A5_A5A5);
        for (i, cell) in sig.iter_mut().enumerate() {
            let v = self.derived(i, h1, h2);
            *cell = v.min(*cell);
        }
    }

    /// Compute the 64-component `MinHash` signature of `text`.
    ///
    /// Matches the C++ `compute_signature_`: text shorter than the shingle
    /// width is padded with NUL bytes to one shingle; empty text yields the
    /// all-`0xFFFF_FFFF` signature; otherwise every length-`k` window is folded
    /// in.
    #[must_use]
    pub fn compute_signature(&self, text: &str) -> Signature {
        let bytes = text.as_bytes();
        let mut sig = EMPTY_SIGNATURE;
        if bytes.len() < SHINGLE_WIDTH {
            if bytes.is_empty() {
                return sig;
            }
            let mut padded = bytes.to_vec();
            padded.resize(SHINGLE_WIDTH, 0);
            self.fold_shingle(&mut sig, &padded);
            return sig;
        }
        let n_shingles = bytes.len() - SHINGLE_WIDTH + 1;
        for off in 0..n_shingles {
            self.fold_shingle(&mut sig, &bytes[off..off + SHINGLE_WIDTH]);
        }
        sig
    }

    /// The public `minhash(text)` accessor: signature without inserting.
    #[must_use]
    pub fn minhash(&self, text: &str) -> Signature {
        self.compute_signature(text)
    }

    /// Band hash for `band`: FNV reduction over that band's signature rows,
    /// byte-identical to the C++ `compute_band_hash_`.
    #[must_use]
    fn band_hash(sig: &Signature, band: usize) -> u64 {
        let start = band * ROWS_PER_BAND;
        let mut h = 0xCBF2_9CE4_8422_2325 ^ (band as u64);
        for r in 0..ROWS_PER_BAND {
            h ^= u64::from(sig[start + r]);
            h = h.wrapping_mul(0x0000_0100_0000_01B3);
        }
        h
    }

    fn insert_into_bands(&mut self, slot: usize) {
        let sig = self.signatures[slot];
        for band in 0..BANDS {
            let bh = Self::band_hash(&sig, band);
            self.band_index[band].entry(bh).or_default().push(slot);
        }
    }

    fn remove_from_bands(&mut self, slot: usize) {
        let sig = self.signatures[slot];
        for band in 0..BANDS {
            let bh = Self::band_hash(&sig, band);
            if let Some(slots) = self.band_index[band].get_mut(&bh) {
                slots.retain(|&s| s != slot);
                if slots.is_empty() {
                    self.band_index[band].remove(&bh);
                }
            }
        }
    }

    /// Insert or overwrite `(entry_id, text)`.
    ///
    /// Idempotent on `entry_id`: a re-add recomputes the signature and rewires
    /// its band membership. Returns `false` only when the index is full (at
    /// `max_entries` with no free slot); otherwise stores and returns `true`.
    pub fn add_entry(&mut self, entry_id: u64, text: &str) -> bool {
        if let Some(&slot) = self.id_to_slot.get(&entry_id) {
            self.remove_from_bands(slot);
            self.signatures[slot] = self.compute_signature(text);
            self.insert_into_bands(slot);
            self.slot_to_entry_id[slot] = entry_id;
            return true;
        }
        if self.signatures.len() >= self.max_entries && self.free_slots.is_empty() {
            return false;
        }
        let sig = self.compute_signature(text);
        let slot = if let Some(slot) = self.free_slots.pop() {
            self.signatures[slot] = sig;
            self.slot_to_entry_id[slot] = entry_id;
            slot
        } else {
            let slot = self.signatures.len();
            self.signatures.push(sig);
            self.slot_to_entry_id.push(entry_id);
            slot
        };
        self.id_to_slot.insert(entry_id, slot);
        self.insert_into_bands(slot);
        true
    }

    /// Remove `entry_id`. Returns whether it was present. A removed slot's
    /// signature is wiped to the all-`0xFFFF_FFFF` sentinel and its
    /// `slot_to_entry_id` set to `u64::MAX` so a band collision cannot resurrect
    /// it.
    pub fn remove_entry(&mut self, entry_id: u64) -> bool {
        let Some(slot) = self.id_to_slot.remove(&entry_id) else {
            return false;
        };
        self.remove_from_bands(slot);
        self.free_slots.push(slot);
        self.signatures[slot] = EMPTY_SIGNATURE;
        if slot < self.slot_to_entry_id.len() {
            self.slot_to_entry_id[slot] = EMPTY_SLOT;
        }
        true
    }

    /// Estimated Jaccard resemblance of two signatures: matching positions / 64.
    #[must_use]
    fn jaccard_estimate(a: &Signature, b: &Signature) -> f32 {
        // Accumulate the match count directly into a `u16` (max 64, so no
        // truncation) and divide by the constant 64. Both operands are tiny and
        // exactly representable in f32, so `f32::from` is lossless and clippy's
        // cast-precision lints stay satisfied without an allow attribute. This
        // is `matches / 64`, the MinHash Jaccard estimate.
        // The divisor is the signature length as a float. SIGNATURE_LEN is the
        // compile-time constant 64; this assert pins the literal below to it so
        // a future change to the constant cannot silently desync the divisor.
        const _: () = assert!(SIGNATURE_LEN == 64);
        let mut matches: u16 = 0;
        for (x, y) in a.iter().zip(b.iter()) {
            if x == y {
                matches += 1;
            }
        }
        f32::from(matches) / 64.0_f32
    }

    /// `(entry_id, similarity)` pairs with `similarity >= threshold`, sorted by
    /// similarity descending.
    ///
    /// Only entries that collided in at least one LSH band are scored. Wiped
    /// slots (sentinel `u64::MAX`) are skipped. Ties keep their first-seen
    /// (band-scan) order via a stable sort; the C++ `std::sort` left ties
    /// unspecified, so this is a contract-safe tightening.
    #[must_use]
    pub fn find_similar(&self, text: &str, threshold: f32) -> Vec<(u64, f32)> {
        let query = self.compute_signature(text);
        let mut seen = vec![false; self.signatures.len()];
        let mut candidates: Vec<usize> = Vec::new();
        for band in 0..BANDS {
            let bh = Self::band_hash(&query, band);
            if let Some(slots) = self.band_index[band].get(&bh) {
                for &slot in slots {
                    if slot < seen.len() && !seen[slot] {
                        seen[slot] = true;
                        candidates.push(slot);
                    }
                }
            }
        }
        let mut out: Vec<(u64, f32)> = Vec::with_capacity(candidates.len());
        for slot in candidates {
            if slot >= self.slot_to_entry_id.len() {
                continue;
            }
            let entry_id = self.slot_to_entry_id[slot];
            if entry_id == EMPTY_SLOT {
                continue;
            }
            let sim = Self::jaccard_estimate(&query, &self.signatures[slot]);
            if sim < threshold {
                continue;
            }
            out.push((entry_id, sim));
        }
        out.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        out
    }

    /// Whether any indexed entry clears `threshold`.
    #[must_use]
    pub fn has_duplicate(&self, text: &str, threshold: f32) -> bool {
        !self.find_similar(text, threshold).is_empty()
    }

    /// Number of live entries.
    #[must_use]
    pub fn size(&self) -> usize {
        self.id_to_slot.len()
    }

    /// Estimated heap bytes held. An estimate, not a cross-language contract.
    #[must_use]
    pub fn memory_bytes(&self) -> usize {
        let mut total = std::mem::size_of::<Self>();
        total += self.signatures.capacity() * std::mem::size_of::<Signature>();
        total += self.id_to_slot.len()
            * (std::mem::size_of::<u64>() + std::mem::size_of::<usize>() + 16);
        total += self.free_slots.capacity() * std::mem::size_of::<usize>();
        for band in &self.band_index {
            for slots in band.values() {
                total += std::mem::size_of::<u64>()
                    + std::mem::size_of::<Vec<usize>>()
                    + slots.capacity() * std::mem::size_of::<usize>()
                    + 16;
            }
        }
        total
    }

    /// Drop all entries and band indexes.
    pub fn clear(&mut self) {
        self.signatures.clear();
        self.id_to_slot.clear();
        self.slot_to_entry_id.clear();
        self.free_slots.clear();
        for band in &mut self.band_index {
            band.clear();
        }
    }

    /// Serialise the index to the C++ binary snapshot layout (little-endian):
    /// `magic u64`, `version u32`, `seed u64`, `entry_count u64`, then per live
    /// entry `entry_id u64` + 64 × `u32` signature components.
    ///
    /// # Errors
    ///
    /// Returns [`DedupError::SaveOpen`] if the temp file cannot be written. The
    /// write is atomic (temp file + rename), matching the C++ kernel.
    pub fn save(&self, path: &Path) -> Result<(), DedupError> {
        let mut buf: Vec<u8> = Vec::new();
        write_u64(&mut buf, SNAPSHOT_MAGIC);
        write_u32(&mut buf, SNAPSHOT_VERSION);
        write_u64(&mut buf, self.seed);
        write_u64(&mut buf, self.id_to_slot.len() as u64);
        for (&entry_id, &slot) in &self.id_to_slot {
            write_u64(&mut buf, entry_id);
            for &component in &self.signatures[slot] {
                write_u32(&mut buf, component);
            }
        }
        let tmp = append_suffix(path, ".tmp");
        write_all_to(&tmp, &buf).map_err(|_| DedupError::SaveOpen)?;
        fs::rename(&tmp, path).map_err(|_| DedupError::SaveOpen)?;
        Ok(())
    }

    /// Replace the index contents from a snapshot written by [`Self::save`] (or
    /// the C++ kernel).
    ///
    /// # Errors
    ///
    /// - [`DedupError::LoadOpen`] if the file cannot be opened/read.
    /// - [`SnapshotError::MagicMismatch`] if the magic header is wrong.
    /// - [`SnapshotError::UnsupportedVersion`] if the version is not 1.
    pub fn load(&mut self, path: &Path) -> Result<(), DedupError> {
        let bytes = fs::read(path).map_err(|_| DedupError::LoadOpen)?;
        let mut cur = io::Cursor::new(bytes);
        let magic = read_u64(&mut cur).map_err(|_| DedupError::LoadOpen)?;
        let version = read_u32(&mut cur).map_err(|_| DedupError::LoadOpen)?;
        let seed = read_u64(&mut cur).map_err(|_| DedupError::LoadOpen)?;
        let entry_count = read_u64(&mut cur).map_err(|_| DedupError::LoadOpen)?;
        if magic != SNAPSHOT_MAGIC {
            return Err(DedupError::MagicMismatch);
        }
        if version != SNAPSHOT_VERSION {
            return Err(DedupError::UnsupportedVersion);
        }
        self.clear();
        self.seed = seed;
        self.family = HashFamily::for_seed(seed);
        for _ in 0..entry_count {
            let entry_id = read_u64(&mut cur).map_err(|_| DedupError::LoadOpen)?;
            let mut sig = EMPTY_SIGNATURE;
            for component in &mut sig {
                *component = read_u32(&mut cur).map_err(|_| DedupError::LoadOpen)?;
            }
            let slot = self.signatures.len();
            self.signatures.push(sig);
            self.slot_to_entry_id.push(entry_id);
            self.id_to_slot.insert(entry_id, slot);
            self.insert_into_bands(slot);
        }
        Ok(())
    }
}

// --- little-endian byte helpers (match the C++ raw `write`/`read`) ---

fn write_u32(buf: &mut Vec<u8>, v: u32) {
    buf.extend_from_slice(&v.to_le_bytes());
}

fn write_u64(buf: &mut Vec<u8>, v: u64) {
    buf.extend_from_slice(&v.to_le_bytes());
}

fn read_u32(cur: &mut io::Cursor<Vec<u8>>) -> io::Result<u32> {
    let mut b = [0_u8; 4];
    cur.read_exact(&mut b)?;
    Ok(u32::from_le_bytes(b))
}

fn read_u64(cur: &mut io::Cursor<Vec<u8>>) -> io::Result<u64> {
    let mut b = [0_u8; 8];
    cur.read_exact(&mut b)?;
    Ok(u64::from_le_bytes(b))
}

fn write_all_to(path: &Path, buf: &[u8]) -> io::Result<()> {
    let mut f = fs::File::create(path)?;
    f.write_all(buf)?;
    f.sync_all()
}

fn append_suffix(path: &Path, suffix: &str) -> std::path::PathBuf {
    let mut s = path.as_os_str().to_os_string();
    s.push(suffix);
    std::path::PathBuf::from(s)
}

/// Python-facing dedup index. Thin wrapper over [`DedupIndexCore`] that adapts
/// the Python boundary (exception types, default args) only.
#[pyclass]
pub struct DedupIndex {
    core: DedupIndexCore,
}

#[pymethods]
impl DedupIndex {
    /// `DedupIndex(max_entries=100000, seed=42)`.
    ///
    /// Raises `ValueError` with the safety-cap message when
    /// `max_entries > 100000`.
    #[new]
    #[pyo3(signature = (max_entries=MAX_ENTRIES_CAP, seed=42))]
    fn new(max_entries: usize, seed: u64) -> PyResult<Self> {
        let core = DedupIndexCore::new(max_entries, seed)
            .map_err(|e| PyValueError::new_err(e.message()))?;
        Ok(Self { core })
    }

    /// `minhash(text) -> list[int]` — the 64 `MinHash` components.
    fn minhash(&self, text: &str) -> Vec<u32> {
        self.core.minhash(text).to_vec()
    }

    /// `add_entry(entry_id, text) -> bool`.
    fn add_entry(&mut self, entry_id: u64, text: &str) -> bool {
        self.core.add_entry(entry_id, text)
    }

    /// `remove_entry(entry_id) -> bool`.
    fn remove_entry(&mut self, entry_id: u64) -> bool {
        self.core.remove_entry(entry_id)
    }

    /// `find_similar(text, threshold=0.85) -> list[tuple[int, float]]`.
    #[pyo3(signature = (text, threshold=0.85))]
    fn find_similar(&self, text: &str, threshold: f32) -> Vec<(u64, f32)> {
        self.core.find_similar(text, threshold)
    }

    /// `has_duplicate(text, threshold=0.85) -> bool`.
    #[pyo3(signature = (text, threshold=0.85))]
    fn has_duplicate(&self, text: &str, threshold: f32) -> bool {
        self.core.has_duplicate(text, threshold)
    }

    /// `save(path) -> None`. Raises `RuntimeError` if the path cannot be opened.
    fn save(&self, path: &str) -> PyResult<()> {
        self.core
            .save(Path::new(path))
            .map_err(|e| PyRuntimeError::new_err(e.message()))
    }

    /// `load(path) -> None`. Raises `RuntimeError` on open / magic / version
    /// failure.
    fn load(&mut self, path: &str) -> PyResult<()> {
        self.core
            .load(Path::new(path))
            .map_err(|e| PyRuntimeError::new_err(e.message()))
    }

    /// `size() -> int`.
    fn size(&self) -> usize {
        self.core.size()
    }

    /// `memory_bytes() -> int`.
    fn memory_bytes(&self) -> usize {
        self.core.memory_bytes()
    }

    /// `clear() -> None`.
    fn clear(&mut self) {
        self.core.clear();
    }
}

/// The Python module. Name MUST equal the `[lib] name` so the artifact imports
/// as `extensions.papertrail_dedup`. The health probe checks for the
/// `DedupIndex` class attribute.
#[pymodule]
fn papertrail_dedup(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<DedupIndex>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{DedupError, DedupIndexCore, Mt19937_64, EMPTY_SIGNATURE, SIGNATURE_LEN};

    fn core() -> DedupIndexCore {
        DedupIndexCore::new(1000, 42).unwrap()
    }

    #[test]
    fn mt19937_64_matches_reference_first_outputs() {
        // Reference values for std::mt19937_64 seeded with 5489 (the default
        // seed), from the C++11 standard's documented test vector lineage. The
        // 10000th output of the default-seeded generator is 9981545732273789042.
        let mut rng = Mt19937_64::new(5489);
        let mut last = 0;
        for _ in 0..10_000 {
            last = rng.next_u64();
        }
        assert_eq!(last, 9_981_545_732_273_789_042);
    }

    #[test]
    fn constructor_rejects_over_cap() {
        // Boundary: 100_001 must error, 100_000 must succeed. Kills a
        // `> -> >=` mutant on the cap guard.
        match DedupIndexCore::new(100_001, 42) {
            Err(e) => assert_eq!(e, DedupError::CapExceeded),
            Ok(_) => panic!("100_001 must exceed the cap"),
        }
        assert!(DedupIndexCore::new(100_000, 42).is_ok());
    }

    #[test]
    fn identical_text_is_self_similar_above_any_threshold() {
        let mut idx = core();
        idx.add_entry(1, "the quick brown fox jumps over the lazy dog");
        let hits = idx.find_similar("the quick brown fox jumps over the lazy dog", 0.85);
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].0, 1);
        assert!(
            (hits[0].1 - 1.0).abs() < f32::EPSILON,
            "self Jaccard must be 1.0"
        );
    }

    #[test]
    fn distinct_text_below_threshold_is_not_returned() {
        let mut idx = core();
        idx.add_entry(1, "completely unrelated subject about astronomy and stars");
        let hits = idx.find_similar("a totally different topic concerning marine biology", 0.85);
        assert!(
            hits.is_empty(),
            "unrelated text must not clear 0.85, got {hits:?}"
        );
    }

    #[test]
    fn near_duplicate_collapses_at_default_threshold() {
        let mut idx = core();
        let base = "The paper-trail dedup index collapses near duplicate abstracts together.";
        let near = "The paper-trail dedup index collapses near duplicate abstracts together!!";
        idx.add_entry(7, base);
        let hits = idx.find_similar(near, 0.85);
        assert!(
            hits.iter().any(|&(id, _)| id == 7),
            "near-dup must be found, got {hits:?}"
        );
    }

    #[test]
    fn add_entry_is_idempotent_on_id() {
        let mut idx = core();
        assert!(idx.add_entry(3, "first version of the text content here"));
        assert!(idx.add_entry(3, "first version of the text content here"));
        assert_eq!(idx.size(), 1, "re-adding the same id must not grow size");
    }

    #[test]
    fn add_entry_overwrites_signature_on_readd() {
        let mut idx = core();
        idx.add_entry(5, "alpha alpha alpha alpha alpha original text body");
        idx.add_entry(5, "zeta zeta zeta zeta zeta completely replaced body");
        // The new text must self-match; the old text must no longer match.
        assert!(idx
            .find_similar("zeta zeta zeta zeta zeta completely replaced body", 0.85)
            .iter()
            .any(|&(id, _)| id == 5));
        assert!(idx
            .find_similar("alpha alpha alpha alpha alpha original text body", 0.85)
            .is_empty());
    }

    #[test]
    fn remove_entry_reports_presence_and_wipes() {
        let mut idx = core();
        idx.add_entry(9, "some text to remove afterwards from the index");
        assert!(idx.remove_entry(9), "present id must report true");
        assert!(!idx.remove_entry(9), "absent id must report false");
        assert_eq!(idx.size(), 0);
        // A removed entry must not resurface via band collision.
        assert!(idx
            .find_similar("some text to remove afterwards from the index", 0.85)
            .is_empty());
    }

    #[test]
    fn capacity_full_rejects_new_but_allows_readd() {
        let mut idx = DedupIndexCore::new(2, 42).unwrap();
        assert!(idx.add_entry(1, "first entry text content padded out here"));
        assert!(idx.add_entry(2, "second entry text content padded out here"));
        assert!(
            !idx.add_entry(3, "third entry over capacity rejected here"),
            "full must reject"
        );
        assert!(
            idx.add_entry(1, "re-add existing id even when full is fine"),
            "re-add ok when full"
        );
    }

    #[test]
    fn freed_slot_is_reused() {
        let mut idx = DedupIndexCore::new(2, 42).unwrap();
        idx.add_entry(1, "first entry text content padded out here");
        idx.add_entry(2, "second entry text content padded out here");
        assert!(idx.remove_entry(1));
        // A free slot now exists, so a new id is accepted even though len==2.
        assert!(idx.add_entry(3, "third entry now fits the reclaimed slot here"));
        assert_eq!(idx.size(), 2);
    }

    #[test]
    fn empty_text_signature_is_all_sentinel() {
        let idx = core();
        assert_eq!(idx.minhash(""), EMPTY_SIGNATURE);
    }

    #[test]
    fn short_text_is_padded_not_panicking() {
        let idx = core();
        // Shorter than the 5-char shingle width: must not panic and must
        // produce a non-sentinel signature.
        let sig = idx.minhash("ab");
        assert_ne!(sig, EMPTY_SIGNATURE, "non-empty short text must hash");
    }

    #[test]
    fn find_similar_sorted_descending() {
        let mut idx = core();
        let exact = "The dedup index sorts its results by similarity descending order.";
        let near = "The dedup index sorts its results by similarity descending ORDER!!";
        idx.add_entry(1, near);
        idx.add_entry(2, exact);
        let hits = idx.find_similar(exact, 0.5);
        assert!(hits.len() >= 2, "both should be candidates, got {hits:?}");
        for w in hits.windows(2) {
            assert!(w[0].1 >= w[1].1, "not sorted descending: {hits:?}");
        }
        assert_eq!(hits[0].0, 2, "the exact match must rank first");
    }

    #[test]
    fn save_then_load_round_trips() {
        let dir = std::env::temp_dir().join(format!("pt_dedup_rt_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("snap.idx");
        let mut idx = core();
        idx.add_entry(11, "first persisted abstract with enough length to shingle");
        idx.add_entry(22, "second persisted abstract distinct from the first one");
        idx.save(&path).unwrap();

        let mut restored = core();
        restored.load(&path).unwrap();
        assert_eq!(restored.size(), 2);
        assert!(restored
            .find_similar(
                "first persisted abstract with enough length to shingle",
                0.85
            )
            .iter()
            .any(|&(id, _)| id == 11));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_rejects_bad_magic() {
        let dir = std::env::temp_dir().join(format!("pt_dedup_magic_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("bad.idx");
        std::fs::write(&path, vec![0_u8; 32]).unwrap();
        let mut idx = core();
        assert_eq!(idx.load(&path).unwrap_err(), DedupError::MagicMismatch);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_rejects_unsupported_version() {
        let dir = std::env::temp_dir().join(format!("pt_dedup_ver_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("ver.idx");
        let mut buf: Vec<u8> = Vec::new();
        buf.extend_from_slice(&super::SNAPSHOT_MAGIC.to_le_bytes());
        buf.extend_from_slice(&2_u32.to_le_bytes()); // unsupported version
        buf.extend_from_slice(&42_u64.to_le_bytes());
        buf.extend_from_slice(&0_u64.to_le_bytes());
        std::fs::write(&path, buf).unwrap();
        let mut idx = core();
        assert_eq!(idx.load(&path).unwrap_err(), DedupError::UnsupportedVersion);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_missing_file_errors() {
        let mut idx = core();
        let err = idx
            .load(std::path::Path::new("/nonexistent/path/does/not/exist.idx"))
            .unwrap_err();
        assert_eq!(err, DedupError::LoadOpen);
    }

    #[test]
    fn jaccard_estimate_counts_matches_over_64() {
        let mut a = EMPTY_SIGNATURE;
        let mut b = EMPTY_SIGNATURE;
        // Make exactly 32 of 64 positions match.
        for i in 0..SIGNATURE_LEN {
            let iv = u32::try_from(i).unwrap();
            a[i] = iv;
            b[i] = if i < 32 { iv } else { iv + 1000 };
        }
        let sim = DedupIndexCore::jaccard_estimate(&a, &b);
        assert!(
            (sim - 0.5).abs() < f32::EPSILON,
            "32/64 must be 0.5, got {sim}"
        );
    }

    #[test]
    fn signature_is_deterministic_across_instances() {
        let a = core().minhash("a deterministic abstract that must hash identically");
        let b = core().minhash("a deterministic abstract that must hash identically");
        assert_eq!(a, b);
    }

    #[test]
    fn has_duplicate_matches_find_similar_emptiness() {
        let mut idx = core();
        idx.add_entry(
            1,
            "a stored abstract used to test has_duplicate behaviour here",
        );
        assert!(idx.has_duplicate(
            "a stored abstract used to test has_duplicate behaviour here",
            0.85
        ));
        assert!(!idx.has_duplicate(
            "an entirely orthogonal sentence about volcanoes erupting",
            0.85
        ));
    }
}
