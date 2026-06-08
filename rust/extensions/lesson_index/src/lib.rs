//! Three-sub-index in-process cache hot-path kernel, ported from the C++
//! `lesson_index` kernel (`backend/extensions/lesson_index.cpp` plus
//! `include/lesson_index.h`) to Rust and exposed to Python as the native module
//! `extensions.lesson_index` via `PyO3`.
//!
//! Three caches back the paper-trail / lesson workflow:
//!
//! - `ScopedLessonIndex` — a path-keyed store of resolved-AutoIssue lessons with
//!   a prefix-match `find_by_path` sorted by `(severity desc, resolved_at desc)`.
//! - `PerfBaselineCache` — a `fn_sig` → performance-baseline map.
//! - `CitationCache` — a minimal capacity-managed cache; only `size` /
//!   `memory_bytes` / `reclaim_now` / `clear` are exposed (the Python service
//!   keeps the citation data in a pure-Python dict).
//!
//! ## Parity (port note)
//!
//! Parity is the BEHAVIOURAL CONTRACT, not byte equality. No caller reads a
//! C++-written snapshot from a different process — each process saves and loads
//! its own snapshot — so this port keeps a self-consistent binary format with
//! the same 24-byte header (magic `0x494C4658`, version `1`, payload size,
//! CRC-32C, reserved) written atomically (tmp + rename). `load` raises
//! `RuntimeError` on a missing file, magic/version mismatch, CRC mismatch, or
//! truncation. CRC-32C follows RFC 3309 (Castagnoli polynomial `0x82F63B78`)
//! and `crc32c("") == 0`. The `find_by_path` prefix-match + `(severity desc,
//! resolved_at desc)` sort, the capacity guards, and the binding surface match
//! the C++ kernel. `BTreeMap` provides the ordered prefix walk that the C++
//! `std::map` `lower_bound` loop used.

// Serialization length prefixes round-trip through `u32`/`u64` and the payload
// size is read back as `usize`. These conversions cannot realistically truncate:
// a single snapshot small enough to fit in memory has well under 2^32 entries
// and the on-disk `payload_size` is bounded by the file length. The casts are
// allowed crate-wide for this serialization-only code.
#![allow(clippy::cast_possible_truncation)]

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::io::Write;
use std::path::Path;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

/// Plain-Rust snapshot failure. Kept free of any `PyO3` type so the cores and
/// the snapshot helpers stay unit-testable without linking libpython (mirrors
/// `count_min_sketch` core, whose methods never touch `PyResult`). The thin
/// `#[pymethods]` `save`/`load` wrappers convert this into a `RuntimeError` at
/// the Python boundary; the messages match the former `PyRuntimeError` strings
/// so caller-visible behaviour is unchanged.
#[derive(Debug)]
enum SnapshotError {
    /// An `std::io` failure with a context prefix (open/create/write/rename).
    Io(String),
    /// A format-validation failure (magic / version / truncation / CRC / UTF-8).
    Format(&'static str),
    /// A format-validation failure carrying a dynamic detail (e.g. version N).
    FormatOwned(String),
}

impl SnapshotError {
    fn message(&self) -> String {
        match self {
            SnapshotError::Io(m) | SnapshotError::FormatOwned(m) => m.clone(),
            SnapshotError::Format(m) => (*m).to_owned(),
        }
    }
}

/// Convert a plain-Rust snapshot result into a `PyResult`, raising
/// `RuntimeError` at the Python boundary only.
fn to_py<T>(result: Result<T, SnapshotError>) -> PyResult<T> {
    result.map_err(|e| PyRuntimeError::new_err(e.message()))
}

/// Snapshot magic — "XFLI" little-endian, matching the C++ `kSnapshotMagic`.
const SNAPSHOT_MAGIC: u32 = 0x494C_4658;
/// Snapshot format version, matching the C++ `kSnapshotVersion`.
const SNAPSHOT_VERSION: u32 = 1;
/// Per-instance memory cap (512 MiB), matching the C++ `kMemoryCapBytes`. This
/// is the health-probe attribute the runtime checks for.
const MEMORY_CAP_BYTES: u64 = 512 * 1024 * 1024;
/// Default capacities, matching the C++ `kDefaultMaxEntries` per class.
const SCOPED_DEFAULT_MAX: usize = 1_000_000;
const PERF_DEFAULT_MAX: usize = 50_000;
const CITATION_DEFAULT_MAX: usize = 10_000;

// ── CRC-32C (RFC 3309, Castagnoli) ────────────────────────────────────────

/// CRC-32C reversed Castagnoli polynomial (RFC 3309).
const CRC32C_POLY: u32 = 0x82F6_3B78;

/// CRC-32C of a byte slice (RFC 3309, reversed Castagnoli polynomial
/// `0x82F63B78`). Returns `0` for an empty slice, matching `crc32c("") == 0`.
#[must_use]
pub fn crc32c(data: &[u8]) -> u32 {
    if data.is_empty() {
        return 0;
    }
    let mut crc: u32 = 0xFFFF_FFFF;
    for &byte in data {
        let mut acc = (crc ^ u32::from(byte)) & 0xFF;
        for _ in 0..8 {
            // `0u32.wrapping_sub(acc & 1)` is `-(acc & 1)` as a mask: all ones
            // when the low bit is set, all zeros otherwise — matching the C++
            // `(0U - (crc & 1U))` branchless table step.
            acc = (acc >> 1) ^ (CRC32C_POLY & 0u32.wrapping_sub(acc & 1));
        }
        crc = (crc >> 8) ^ acc;
    }
    crc ^ 0xFFFF_FFFF
}

// ── Snapshot header + helpers ─────────────────────────────────────────────

/// Build the 24-byte snapshot header for a payload.
fn snapshot_header(payload: &[u8]) -> [u8; 24] {
    let mut hdr = [0u8; 24];
    hdr[0..4].copy_from_slice(&SNAPSHOT_MAGIC.to_le_bytes());
    hdr[4..8].copy_from_slice(&SNAPSHOT_VERSION.to_le_bytes());
    hdr[8..16].copy_from_slice(&(payload.len() as u64).to_le_bytes());
    hdr[16..20].copy_from_slice(&crc32c(payload).to_le_bytes());
    // bytes 20..24 are the reserved field, left zero.
    hdr
}

/// Write a payload to `path` atomically: header + payload to `path.tmp`, then
/// rename. Creates the parent directory. Maps I/O failure to `RuntimeError`.
fn write_snapshot(path: &Path, payload: &[u8]) -> Result<(), SnapshotError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| SnapshotError::Io(format!("lesson_index: cannot create dir: {e}")))?;
    }
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(".tmp");
    let tmp_path = Path::new(&tmp);
    {
        let mut out = fs::File::create(tmp_path).map_err(|e| {
            SnapshotError::Io(format!("lesson_index: cannot open snapshot for write: {e}"))
        })?;
        out.write_all(&snapshot_header(payload))
            .and_then(|()| out.write_all(payload))
            .map_err(|e| SnapshotError::Io(format!("lesson_index: snapshot write failed: {e}")))?;
    }
    fs::rename(tmp_path, path)
        .map_err(|e| SnapshotError::Io(format!("lesson_index: snapshot rename failed: {e}")))
}

/// Read a snapshot from `path`, validating magic/version/CRC and returning the
/// payload bytes. Maps every failure mode to `RuntimeError` with a message
/// mirroring the C++ kernel.
fn read_snapshot(path: &Path) -> Result<Vec<u8>, SnapshotError> {
    let bytes = fs::read(path).map_err(|e| {
        SnapshotError::Io(format!("lesson_index: cannot open snapshot for read: {e}"))
    })?;
    if bytes.len() < 24 {
        return Err(SnapshotError::Format(
            "lesson_index: snapshot magic mismatch (corrupt or wrong format)",
        ));
    }
    let magic = u32::from_le_bytes(bytes[0..4].try_into().unwrap());
    if magic != SNAPSHOT_MAGIC {
        return Err(SnapshotError::Format(
            "lesson_index: snapshot magic mismatch (corrupt or wrong format)",
        ));
    }
    let version = u32::from_le_bytes(bytes[4..8].try_into().unwrap());
    if version != SNAPSHOT_VERSION {
        return Err(SnapshotError::FormatOwned(format!(
            "lesson_index: snapshot version {version} unsupported"
        )));
    }
    let payload_size = u64::from_le_bytes(bytes[8..16].try_into().unwrap()) as usize;
    let stored_crc = u32::from_le_bytes(bytes[16..20].try_into().unwrap());
    let payload = &bytes[24..];
    if payload.len() < payload_size {
        return Err(SnapshotError::Format(
            "lesson_index: snapshot payload truncated",
        ));
    }
    let payload = &payload[..payload_size];
    if crc32c(payload) != stored_crc {
        return Err(SnapshotError::Format(
            "lesson_index: snapshot CRC mismatch — file is corrupt",
        ));
    }
    Ok(payload.to_vec())
}

/// A little cursor over a payload that reads length-prefixed strings and PODs,
/// erroring on overrun.
struct Cursor<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Cursor<'a> {
    fn new(buf: &'a [u8]) -> Self {
        Self { buf, pos: 0 }
    }

    fn take(&mut self, n: usize) -> Result<&'a [u8], SnapshotError> {
        if self.pos + n > self.buf.len() {
            return Err(SnapshotError::Format(
                "lesson_index: snapshot payload truncated",
            ));
        }
        let slice = &self.buf[self.pos..self.pos + n];
        self.pos += n;
        Ok(slice)
    }

    fn u32(&mut self) -> Result<u32, SnapshotError> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }

    fn u64(&mut self) -> Result<u64, SnapshotError> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }

    fn i64(&mut self) -> Result<i64, SnapshotError> {
        Ok(i64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }

    fn u8(&mut self) -> Result<u8, SnapshotError> {
        Ok(self.take(1)?[0])
    }

    fn string(&mut self) -> Result<String, SnapshotError> {
        let len = self.u32()? as usize;
        let raw = self.take(len)?;
        String::from_utf8(raw.to_vec())
            .map_err(|_| SnapshotError::Format("lesson_index: snapshot string not valid UTF-8"))
    }
}

fn put_string(buf: &mut Vec<u8>, s: &str) {
    buf.extend_from_slice(&(s.len() as u32).to_le_bytes());
    buf.extend_from_slice(s.as_bytes());
}

// ── Record types ──────────────────────────────────────────────────────────

/// One scoped-lesson record (POD).
#[pyclass]
#[derive(Clone, Copy, Default)]
pub struct LessonRecord {
    #[pyo3(get, set)]
    pub autoissue_id: u64,
    #[pyo3(get, set)]
    pub lesson_hash: u64,
    #[pyo3(get, set)]
    pub severity: u8,
    #[pyo3(get, set)]
    pub resolved_at_unix: i64,
}

#[pymethods]
impl LessonRecord {
    #[new]
    fn new() -> Self {
        Self::default()
    }
}

/// One performance-baseline record (POD).
#[pyclass]
#[derive(Clone, Copy, Default)]
pub struct BaselineRecord {
    #[pyo3(get, set)]
    pub p50_ns: u64,
    #[pyo3(get, set)]
    pub p95_ns: u64,
    #[pyo3(get, set)]
    pub p99_ns: u64,
    #[pyo3(get, set)]
    pub mean_ns: u64,
    #[pyo3(get, set)]
    pub samples: u32,
    #[pyo3(get, set)]
    pub measured_at_unix: i64,
}

#[pymethods]
impl BaselineRecord {
    #[new]
    fn new() -> Self {
        Self::default()
    }
}

// ── ScopedLessonIndex core ─────────────────────────────────────────────────

/// Plain-Rust scoped-lesson index core. `BTreeMap` keeps paths ordered so the
/// prefix walk mirrors the C++ `std::map` `lower_bound` loop.
#[derive(Default)]
pub struct ScopedLessonCore {
    data: BTreeMap<String, Vec<LessonRecord>>,
    id_to_path: HashMap<u64, String>,
    max_entries: usize,
}

impl ScopedLessonCore {
    #[must_use]
    pub fn new(max_entries: usize) -> Self {
        Self {
            data: BTreeMap::new(),
            id_to_path: HashMap::new(),
            max_entries,
        }
    }

    fn total_entries(&self) -> usize {
        self.data.values().map(Vec::len).sum()
    }

    /// Store a record under `path`. Returns `false` when at capacity.
    pub fn add(&mut self, path: &str, record: LessonRecord) -> bool {
        if self.total_entries() >= self.max_entries {
            return false;
        }
        self.data.entry(path.to_owned()).or_default().push(record);
        self.id_to_path.insert(record.autoissue_id, path.to_owned());
        true
    }

    /// Remove every record with `autoissue_id`. Returns `false` if unknown.
    pub fn remove(&mut self, autoissue_id: u64) -> bool {
        let Some(path) = self.id_to_path.remove(&autoissue_id) else {
            return false;
        };
        if let Some(bucket) = self.data.get_mut(&path) {
            bucket.retain(|r| r.autoissue_id != autoissue_id);
            if bucket.is_empty() {
                self.data.remove(&path);
            }
        }
        true
    }

    /// Prefix-match records whose path starts with `path`, sorted by
    /// `(severity desc, resolved_at desc)`, truncated to `limit`.
    #[must_use]
    pub fn find_by_path(&self, path: &str, limit: usize) -> Vec<LessonRecord> {
        let mut out: Vec<LessonRecord> = Vec::new();
        for (key, recs) in self.data.range(path.to_owned()..) {
            if !key.starts_with(path) {
                break;
            }
            out.extend(recs.iter().copied());
        }
        out.sort_by(|a, b| {
            b.severity
                .cmp(&a.severity)
                .then(b.resolved_at_unix.cmp(&a.resolved_at_unix))
        });
        out.truncate(limit);
        out
    }

    #[must_use]
    pub fn size(&self) -> usize {
        self.total_entries()
    }

    #[must_use]
    pub fn memory_bytes(&self) -> usize {
        let mut total = std::mem::size_of::<Self>();
        for (k, v) in &self.data {
            total += k.len() + v.len() * std::mem::size_of::<LessonRecord>() + 32;
        }
        total += self.id_to_path.len() * (std::mem::size_of::<u64>() + 64);
        total
    }

    pub fn clear(&mut self) {
        self.data.clear();
        self.id_to_path.clear();
    }

    fn serialize(&self) -> Vec<u8> {
        let mut buf = Vec::new();
        buf.extend_from_slice(&(self.data.len() as u64).to_le_bytes());
        for (path, recs) in &self.data {
            put_string(&mut buf, path);
            buf.extend_from_slice(&(recs.len() as u32).to_le_bytes());
            for r in recs {
                buf.extend_from_slice(&r.autoissue_id.to_le_bytes());
                buf.extend_from_slice(&r.lesson_hash.to_le_bytes());
                buf.push(r.severity);
                buf.extend_from_slice(&r.resolved_at_unix.to_le_bytes());
            }
        }
        buf
    }

    fn deserialize(&mut self, payload: &[u8]) -> Result<(), SnapshotError> {
        self.clear();
        let mut cur = Cursor::new(payload);
        let n_paths = cur.u64()?;
        for _ in 0..n_paths {
            let path = cur.string()?;
            let n_recs = cur.u32()?;
            let mut bucket = Vec::with_capacity(n_recs as usize);
            for _ in 0..n_recs {
                let record = LessonRecord {
                    autoissue_id: cur.u64()?,
                    lesson_hash: cur.u64()?,
                    severity: cur.u8()?,
                    resolved_at_unix: cur.i64()?,
                };
                self.id_to_path.insert(record.autoissue_id, path.clone());
                bucket.push(record);
            }
            self.data.insert(path, bucket);
        }
        Ok(())
    }
}

// ── PerfBaselineCache core ──────────────────────────────────────────────────

/// Plain-Rust perf-baseline cache core.
#[derive(Default)]
pub struct PerfBaselineCore {
    data: HashMap<String, BaselineRecord>,
    max_entries: usize,
}

impl PerfBaselineCore {
    #[must_use]
    pub fn new(max_entries: usize) -> Self {
        Self {
            data: HashMap::new(),
            max_entries,
        }
    }

    #[must_use]
    pub fn get(&self, fn_sig: &str) -> Option<BaselineRecord> {
        self.data.get(fn_sig).copied()
    }

    /// Store a baseline. Returns `false` only when the cache is full AND the key
    /// is new (existing keys may always overwrite).
    pub fn put(&mut self, fn_sig: &str, record: BaselineRecord) -> bool {
        if self.data.len() >= self.max_entries && !self.data.contains_key(fn_sig) {
            return false;
        }
        self.data.insert(fn_sig.to_owned(), record);
        true
    }

    pub fn erase(&mut self, fn_sig: &str) -> bool {
        self.data.remove(fn_sig).is_some()
    }

    #[must_use]
    pub fn size(&self) -> usize {
        self.data.len()
    }

    #[must_use]
    pub fn memory_bytes(&self) -> usize {
        let mut total = std::mem::size_of::<Self>();
        for k in self.data.keys() {
            total += k.len() + std::mem::size_of::<BaselineRecord>() + 32;
        }
        total
    }

    pub fn clear(&mut self) {
        self.data.clear();
    }

    fn serialize(&self) -> Vec<u8> {
        let mut buf = Vec::new();
        buf.extend_from_slice(&(self.data.len() as u64).to_le_bytes());
        for (k, v) in &self.data {
            put_string(&mut buf, k);
            buf.extend_from_slice(&v.p50_ns.to_le_bytes());
            buf.extend_from_slice(&v.p95_ns.to_le_bytes());
            buf.extend_from_slice(&v.p99_ns.to_le_bytes());
            buf.extend_from_slice(&v.mean_ns.to_le_bytes());
            buf.extend_from_slice(&v.samples.to_le_bytes());
            buf.extend_from_slice(&v.measured_at_unix.to_le_bytes());
        }
        buf
    }

    fn deserialize(&mut self, payload: &[u8]) -> Result<(), SnapshotError> {
        self.clear();
        let mut cur = Cursor::new(payload);
        let n = cur.u64()?;
        for _ in 0..n {
            let key = cur.string()?;
            let record = BaselineRecord {
                p50_ns: cur.u64()?,
                p95_ns: cur.u64()?,
                p99_ns: cur.u64()?,
                mean_ns: cur.u64()?,
                samples: cur.u32()?,
                measured_at_unix: cur.i64()?,
            };
            self.data.insert(key, record);
        }
        Ok(())
    }
}

// ── PyO3 wrappers ──────────────────────────────────────────────────────────

/// Python-facing scoped-lesson index.
#[pyclass]
pub struct ScopedLessonIndex {
    core: ScopedLessonCore,
}

#[pymethods]
impl ScopedLessonIndex {
    #[new]
    #[pyo3(signature = (max_entries=SCOPED_DEFAULT_MAX))]
    fn new(max_entries: usize) -> Self {
        Self {
            core: ScopedLessonCore::new(max_entries),
        }
    }

    // `PyRef` is the by-reference borrow of a `#[pyclass]`; the `*record` copy
    // is cheap (LessonRecord is `Copy`). clippy's by-value lint does not model
    // the PyO3 extraction, so it is allowed here.
    #[allow(clippy::needless_pass_by_value)]
    fn add(&mut self, path: &str, record: PyRef<'_, LessonRecord>) -> bool {
        self.core.add(path, *record)
    }

    fn remove(&mut self, autoissue_id: u64) -> bool {
        self.core.remove(autoissue_id)
    }

    #[pyo3(signature = (path, limit=5))]
    fn find_by_path(&self, path: &str, limit: usize) -> Vec<LessonRecord> {
        self.core.find_by_path(path, limit)
    }

    fn size(&self) -> usize {
        self.core.size()
    }

    fn memory_bytes(&self) -> usize {
        self.core.memory_bytes()
    }

    fn reclaim_now(&mut self) {
        self.core.clear();
    }

    fn clear(&mut self) {
        self.core.clear();
    }

    fn save(&self, py: Python<'_>, path: &str) -> PyResult<()> {
        let payload = self.core.serialize();
        to_py(py.detach(|| write_snapshot(Path::new(path), &payload)))
    }

    fn load(&mut self, path: &str) -> PyResult<()> {
        let payload = to_py(read_snapshot(Path::new(path)))?;
        to_py(self.core.deserialize(&payload))
    }
}

/// Python-facing perf-baseline cache.
#[pyclass]
pub struct PerfBaselineCache {
    core: PerfBaselineCore,
}

#[pymethods]
impl PerfBaselineCache {
    #[new]
    #[pyo3(signature = (max_entries=PERF_DEFAULT_MAX))]
    fn new(max_entries: usize) -> Self {
        Self {
            core: PerfBaselineCore::new(max_entries),
        }
    }

    fn get(&self, fn_sig: &str) -> Option<BaselineRecord> {
        self.core.get(fn_sig)
    }

    // See `ScopedLessonIndex::add` for why the by-value `PyRef` lint is allowed.
    #[allow(clippy::needless_pass_by_value)]
    fn put(&mut self, fn_sig: &str, record: PyRef<'_, BaselineRecord>) -> bool {
        self.core.put(fn_sig, *record)
    }

    fn erase(&mut self, fn_sig: &str) -> bool {
        self.core.erase(fn_sig)
    }

    fn size(&self) -> usize {
        self.core.size()
    }

    fn memory_bytes(&self) -> usize {
        self.core.memory_bytes()
    }

    fn reclaim_now(&mut self) {
        self.core.clear();
    }

    fn clear(&mut self) {
        self.core.clear();
    }

    fn save(&self, py: Python<'_>, path: &str) -> PyResult<()> {
        let payload = self.core.serialize();
        to_py(py.detach(|| write_snapshot(Path::new(path), &payload)))
    }

    fn load(&mut self, path: &str) -> PyResult<()> {
        let payload = to_py(read_snapshot(Path::new(path)))?;
        to_py(self.core.deserialize(&payload))
    }
}

/// Python-facing citation cache. Deliberately minimal binding: only capacity +
/// memory accounting are exposed (the Python service owns the citation data in a
/// pure-Python dict). It still respects the `max_entries` cap for parity.
#[pyclass]
pub struct CitationCache {
    count: usize,
    #[allow(dead_code)]
    max_entries: usize,
}

#[pymethods]
impl CitationCache {
    #[new]
    #[pyo3(signature = (max_entries=CITATION_DEFAULT_MAX))]
    fn new(max_entries: usize) -> Self {
        Self {
            count: 0,
            max_entries,
        }
    }

    fn size(&self) -> usize {
        self.count
    }

    // Mirrors the C++ `CitationCache::memory_bytes` which reports only the fixed
    // struct overhead through the minimal binding (no entries are ever stored
    // via this binding). `self` is part of the required `#[pymethods]` signature.
    #[allow(clippy::unused_self)]
    fn memory_bytes(&self) -> usize {
        std::mem::size_of::<Self>()
    }

    fn reclaim_now(&mut self) {
        self.count = 0;
    }

    fn clear(&mut self) {
        self.count = 0;
    }
}

/// `memory_cap_bytes() -> int` — the per-instance memory cap (512 MiB). This is
/// the health-probe attribute the runtime checks for.
#[pyfunction]
fn memory_cap_bytes() -> u64 {
    MEMORY_CAP_BYTES
}

/// `memory_bytes_total() -> int` — scaffold returns 0 (per-instance only).
#[pyfunction]
fn memory_bytes_total() -> u64 {
    0
}

/// `reclaim_all() -> None` — scaffold no-op (per-instance `reclaim_now` is the
/// entry point).
#[pyfunction]
fn reclaim_all() {}

/// `crc32c(s: str) -> int` — CRC-32C of the UTF-8 bytes of `s`.
#[pyfunction]
#[pyo3(name = "crc32c")]
fn crc32c_py(s: &str) -> u32 {
    crc32c(s.as_bytes())
}

/// The Python module definition. The module name (`lesson_index`) MUST match
/// the `[lib] name` in `Cargo.toml`. Registering `memory_cap_bytes` keeps the
/// health probe's expected attribute present.
#[pymodule]
fn lesson_index(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<LessonRecord>()?;
    m.add_class::<BaselineRecord>()?;
    m.add_class::<ScopedLessonIndex>()?;
    m.add_class::<PerfBaselineCache>()?;
    m.add_class::<CitationCache>()?;
    m.add_function(wrap_pyfunction!(memory_cap_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(memory_bytes_total, m)?)?;
    m.add_function(wrap_pyfunction!(reclaim_all, m)?)?;
    m.add_function(wrap_pyfunction!(crc32c_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{crc32c, BaselineRecord, LessonRecord, PerfBaselineCore, ScopedLessonCore};

    fn lesson(id: u64, severity: u8, resolved: i64) -> LessonRecord {
        LessonRecord {
            autoissue_id: id,
            lesson_hash: id.wrapping_mul(2_654_435_761),
            severity,
            resolved_at_unix: resolved,
        }
    }

    #[test]
    fn crc32c_empty_is_zero() {
        assert_eq!(crc32c(b""), 0);
    }

    #[test]
    fn crc32c_known_vector() {
        // CRC-32C of the 9-byte ASCII string "123456789" is 0xE3069283 (a
        // standard Castagnoli check value).
        assert_eq!(crc32c(b"123456789"), 0xE306_9283);
    }

    #[test]
    fn scoped_add_and_size() {
        let mut idx = ScopedLessonCore::new(10);
        assert!(idx.add("a/b", lesson(1, 2, 100)));
        assert!(idx.add("a/b", lesson(2, 1, 200)));
        assert_eq!(idx.size(), 2);
    }

    #[test]
    fn scoped_capacity_guard_returns_false() {
        let mut idx = ScopedLessonCore::new(1);
        assert!(idx.add("a", lesson(1, 0, 0)));
        // At capacity: the second add is rejected and not stored.
        assert!(!idx.add("a", lesson(2, 0, 0)));
        assert_eq!(idx.size(), 1);
    }

    #[test]
    fn scoped_remove_unknown_is_false() {
        let mut idx = ScopedLessonCore::new(10);
        assert!(!idx.remove(999));
    }

    #[test]
    fn scoped_remove_deletes_record_and_empty_bucket() {
        let mut idx = ScopedLessonCore::new(10);
        idx.add("a", lesson(1, 0, 0));
        assert!(idx.remove(1));
        assert_eq!(idx.size(), 0);
        // Bucket gone, so a fresh find returns nothing.
        assert!(idx.find_by_path("a", 5).is_empty());
    }

    #[test]
    fn scoped_find_is_prefix_match() {
        let mut idx = ScopedLessonCore::new(10);
        idx.add("apps/audit", lesson(1, 1, 100));
        idx.add("apps/audit/sub", lesson(2, 1, 100));
        idx.add("apps/other", lesson(3, 1, 100));
        // Prefix "apps/audit" matches the first two but not "apps/other".
        let found = idx.find_by_path("apps/audit", 5);
        assert_eq!(found.len(), 2);
    }

    #[test]
    fn scoped_find_sorts_by_severity_then_resolved_desc() {
        let mut idx = ScopedLessonCore::new(10);
        idx.add("p", lesson(1, 1, 100)); // medium, older
        idx.add("p", lesson(2, 3, 50)); // critical, oldest
        idx.add("p", lesson(3, 1, 200)); // medium, newest
        let found = idx.find_by_path("p", 5);
        // critical first; then medium ordered by resolved desc (200 before 100).
        assert_eq!(found[0].autoissue_id, 2);
        assert_eq!(found[1].autoissue_id, 3);
        assert_eq!(found[2].autoissue_id, 1);
    }

    #[test]
    fn scoped_find_truncates_to_limit() {
        let mut idx = ScopedLessonCore::new(10);
        for i in 0..5_u64 {
            idx.add("p", lesson(i, 1, i64::try_from(i).unwrap()));
        }
        assert_eq!(idx.find_by_path("p", 2).len(), 2);
    }

    #[test]
    fn scoped_snapshot_round_trips() {
        let mut idx = ScopedLessonCore::new(10);
        idx.add("apps/audit", lesson(1, 2, 100));
        idx.add("apps/audit", lesson(2, 1, 200));
        idx.add("apps/other", lesson(3, 3, 300));
        let payload = idx.serialize();
        let mut restored = ScopedLessonCore::new(10);
        restored.deserialize(&payload).unwrap();
        assert_eq!(restored.size(), 3);
        let found = restored.find_by_path("apps/audit", 5);
        assert_eq!(found.len(), 2);
        // remove still works after restore (id_to_path rebuilt).
        assert!(restored.remove(3));
        assert_eq!(restored.size(), 2);
    }

    #[test]
    fn perf_get_absent_is_none() {
        let cache = PerfBaselineCore::new(10);
        assert!(cache.get("missing").is_none());
    }

    #[test]
    fn perf_put_get_round_trips() {
        let mut cache = PerfBaselineCore::new(10);
        let rec = BaselineRecord {
            p50_ns: 10,
            p95_ns: 20,
            p99_ns: 30,
            mean_ns: 15,
            samples: 100,
            measured_at_unix: 1234,
        };
        assert!(cache.put("fn", rec));
        let got = cache.get("fn").unwrap();
        assert_eq!(got.p99_ns, 30);
        assert_eq!(got.samples, 100);
    }

    #[test]
    fn perf_put_full_rejects_new_key_allows_overwrite() {
        let mut cache = PerfBaselineCore::new(1);
        assert!(cache.put("a", BaselineRecord::default()));
        // Full + new key -> rejected.
        assert!(!cache.put("b", BaselineRecord::default()));
        // Full + existing key -> allowed (overwrite).
        assert!(cache.put("a", BaselineRecord::default()));
    }

    #[test]
    fn perf_snapshot_round_trips() {
        let mut cache = PerfBaselineCore::new(10);
        let rec = BaselineRecord {
            p50_ns: 1,
            p95_ns: 2,
            p99_ns: 3,
            mean_ns: 4,
            samples: 5,
            measured_at_unix: 6,
        };
        cache.put("sig", rec);
        let payload = cache.serialize();
        let mut restored = PerfBaselineCore::new(10);
        restored.deserialize(&payload).unwrap();
        let got = restored.get("sig").unwrap();
        assert_eq!(got.p95_ns, 2);
        assert_eq!(got.measured_at_unix, 6);
    }
}
