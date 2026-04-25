# Pick #12 — SHA-256 Page Fingerprint (NIST FIPS 180-4)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 12 |
| **Canonical name** | SHA-256 content fingerprint for exact page-body dedup |
| **Settings prefix** | `sha256_fingerprint` |
| **Pipeline stage** | Crawl |
| **Shipped in commit** | **partially shipped** — inline code at [apps/crawler/services/site_crawler.py:210](../../backend/apps/crawler/services/site_crawler.py) uses `hashlib.sha256`; **helper module pending extraction** |
| **Helper module** | [backend/apps/sources/sha256_fingerprint.py](../../backend/apps/sources/sha256_fingerprint.py) |
| **Tests module** | `backend/apps/sources/tests.py` — `SHA256FingerprintTests` (to be created) |
| **Benchmark module** | `backend/benchmarks/test_bench_sha256_fingerprint.py` (pending G6) |

## 2 · Motivation

Between a successful fetch (200) and the bodies the crawler has
already seen (especially on sites that generate near-identical
"loading…" templates for expired threads), we sometimes ingest a
response that's byte-identical to a prior one. Exact dedup via
SHA-256 over the canonicalised body catches those cheaply, before
the body hits NFKC, NFKC hits BGE-M3, and BGE-M3 writes a wasted
embedding. It's complementary to:
- **Bloom Filter (#4)** — ID-level dedup (same post ID seen before).
- **Near-dup clustering (existing META-38)** — fuzzy dedup (two
  paraphrases of the same story) — hundreds of ms per comparison.

SHA-256 over the extracted text is O(n) in page size, computed once
at fetch time, and stored on `CrawledPageMeta.content_hash`.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | National Institute of Standards and Technology. (August 2015). *FIPS 180-4: Secure Hash Standard.* |
| **Open-access link** | <https://csrc.nist.gov/publications/fips/fips180-4/fips-180-4.pdf> |
| **Relevant section(s)** | §6.2 — SHA-256 algorithm description. We call `hashlib.sha256(...).hexdigest()` — stdlib-verified to match. |
| **What we faithfully reproduce** | The algorithm via stdlib. |
| **What we deliberately diverge on** | We hash the **cleaned body text** (after encoding detection + NFKC), not the raw HTTP bytes. Reason: chrome edits (new `<script>` tag, different nonces, ad rotation) change the raw bytes without changing the content, so hashing raw bytes misses dedup opportunities. |

## 4 · Input contract

- **`fingerprint(text: str) -> str`** — returns the 64-char lowercase
  hex SHA-256 digest of `text.encode("utf-8")`.
- **`fingerprint_bytes(data: bytes) -> str`** — returns the digest
  of raw bytes. Use this for binary content (PDF, images) where
  text decoding doesn't apply.
- Empty string is valid input; returns the SHA-256 of the empty
  byte string (`e3b0c44...` — well-known constant).

## 5 · Output contract

- `str` — exactly 64 lowercase hex characters.
- **Invariants.**
  - Same input → same digest, across Python versions and processes.
  - Different inputs → different digests (with 2^-256 collision
    probability, effectively never).
- **Determinism.** Fully deterministic.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `sha256_fingerprint.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no pre-embed dedup; wastes GPU on exact duplicates |
| `sha256_fingerprint.hash_source` | str (enum) | `"cleaned_text"` | Plan-spec diverges from FIPS by hashing cleaned text | No | — | Alternatives: `raw_bytes`, `html_body`, `extracted_main` — corresponds to which stage we hash |
| `sha256_fingerprint.min_text_chars_for_hash` | int | `50` | Empirical — below 50 chars (error pages, placeholders) many pages collide on trivial bodies; skipping them from the dedup hash table prevents false-positive collapses | Yes | `int(10, 500)` | Lower includes more short pages; higher avoids the "empty body" collision cluster |

## 7 · Pseudocode

```
import hashlib

function fingerprint(text):
    data = text.encode("utf-8")
    if len(data) < min_text_chars_for_hash * 4:   # rough UTF-8 byte estimate
        return None                                # signal: too short to dedup on
    return hashlib.sha256(data).hexdigest()

function fingerprint_bytes(data):
    return hashlib.sha256(data).hexdigest()
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py:210` (existing) | `clean_text` | Stored on `CrawledPageMeta.content_hash` |
| `apps/pipeline/services/pipeline_persist.py` | Content before embedding | Skip embed if `content_hash` already present in DB |

**Wiring status.** Partially wired — crawler already computes and
stores the digest. What's missing: a **read-side** dedup check that
consults the hash before scheduling an embed. That lands in W2.

## 9 · Scheduled-updates job

None — inline with crawl.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 MB per hash operation (streaming chunk OK) | — |
| Disk | 32 bytes per stored digest (stored as 64-char hex string = 64 bytes) | — |
| CPU | ~0.5 µs per KB of input (AES-NI helps if available) | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_empty_input_returns_well_known_digest` | Stdlib sanity check |
| `test_same_input_same_digest` | Determinism |
| `test_different_input_different_digest` | Collision-resistance sanity |
| `test_min_text_chars_threshold` | Skip behaviour |
| `test_utf8_encoding_stable_across_normalisation` | NFKC-canon first is the caller's responsibility — helper only hashes bytes |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 KB × 10 000 strings | < 10 ms | > 100 ms |
| medium | 100 KB × 10 000 strings | < 1 s | > 10 s |
| large | 1 MB × 10 000 strings | < 10 s | > 2 min |

## 13 · Edge cases & failure modes

- **Unicode normalisation forms diverge** — caller must NFKC
  normalise first; otherwise `"café"` (NFC) and `"café"` (NFD)
  produce different digests.
- **Hash migration** — if the project ever moves away from SHA-256
  (e.g. SHA-3), stored digests are incompatible; a migration script
  would rehash at ingest. Not planned.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #7 Trafilatura | Clean body is the hash input |
| #13 NFKC | Must run before hashing for cross-encoding dedup |

| Downstream | Reason |
|---|---|
| #4 Bloom Filter | Orthogonal dedup dimension (ID vs content) |
| META-38 near-dup clustering | SHA-256 catches exact; near-dup catches fuzzy |

## 15 · Governance checklist

- [ ] `sha256_fingerprint.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Inline hash computation exists (partial)
- [ ] Helper module extracted
- [ ] Benchmark module
- [ ] Test module
- [ ] Read-side dedup lookup wired (W2)
