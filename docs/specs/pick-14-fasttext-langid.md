# Pick #14 — FastText Language Identification

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 14 |
| **Canonical name** | FastText LangID — `lid.176.bin` model |
| **Settings prefix** | `fasttext_langid` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | **not yet merged — DEFERRED** (awaits `fasttext-langdetect` pip dep + 126 MB model download approval) |
| **Helper module** | `backend/apps/parse/language/fasttext_langid.py` (plan path) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

The linker's corpus is predominantly English but operators run forums
in Japanese, German, Spanish, and Arabic. Embedding Japanese text
with BGE-M3's English tokeniser path underperforms vs. its
multilingual path; surfacing Japanese suggestions to an
English-reading operator via the "similar threads" panel is noise.
Language ID at ingest time lets us route per-language, and filter
out-of-target-language content at rank time. FastText's 176-language
model reaches ~99 % top-1 accuracy on the paper's benchmarks at
~15 MB RAM with a 126 MB on-disk model.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Joulin, A., Grave, E., Bojanowski, P., Douze, M., Jégou, H. & Mikolov, T. (2016). "FastText.zip: Compressing text classification models." *EACL*. |
| **Open-access link** | <https://arxiv.org/abs/1612.03651> |
| **Relevant section(s)** | §3 — hierarchical softmax; §4.3 — `lid.176.bin` benchmarks vs CLD2 / langdetect |
| **What we faithfully reproduce** | We load the shipped `lid.176.bin` and call `predict(text)`. |
| **What we deliberately diverge on** | Plan §Parse & Embed originally hedged to the quantized `lid.176.ftz` (918 KB); operator directive (2026-04-22) is to keep full accuracy, so we use the unquantized model. 126 MB is within the ≤ 256 MB disk budget. |

## 4 · Input contract

- **`detect(text: str, top_k: int = 1) -> list[LangIdResult]`** —
  returns the top-k language guesses.
- `text` should be ≥ 20 characters for reliable detection — the model
  struggles on tweets-length content.

## 5 · Output contract

- `LangIdResult(iso_code: str, confidence: float)` frozen dataclass.
- `iso_code` is ISO 639-1 (e.g. `"en"`, `"ja"`, `"zh-hans"`).
- `confidence` in `[0, 1]`; sum over top-k ≤ 1.
- Empty-string input → `[]`.
- **Determinism.** FastText inference is deterministic; same input →
  same output across restarts.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `fasttext_langid.enabled` | bool | `true` | Recommended preset policy | No | — | Off = treat all text as `en` |
| `fasttext_langid.model_path` | str | `"var/models/lid.176.bin"` | Plan §Parse & Embed — full model chosen by operator 2026-04-22 for accuracy | No | — | Correctness (model identity) |
| `fasttext_langid.min_text_chars` | int | `20` | Joulin et al. §4.3 — below ~20 chars accuracy drops below 90 % | Yes | `int(5, 100)` | Below the floor we skip detection, return `unknown` |
| `fasttext_langid.top_k` | int | `1` | Default — we only need the winner for routing | No | — | Higher asks FastText for more candidates, increases latency |
| `fasttext_langid.confidence_threshold` | float | `0.5` | Empirical — below 0.5 the top-1 guess is unreliable | Yes | `uniform(0.2, 0.9)` | Below threshold, return `unknown` to avoid bad routing |

## 7 · Pseudocode

```
import fasttext

model = fasttext.load_model(settings.model_path)

function detect(text, top_k):
    if len(text) < settings.min_text_chars:
        return [LangIdResult("unknown", 0.0)]
    labels, probs = model.predict(text.replace("\n", " "), k=top_k)
    out = [
        LangIdResult(label.replace("__label__", ""), float(prob))
        for label, prob in zip(labels, probs)
    ]
    if out and out[0].confidence < settings.confidence_threshold:
        return [LangIdResult("unknown", out[0].confidence)]
    return out
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | Extracted body text | Stores `language_code` on `ContentItem`; filters non-target languages downstream |
| `apps/pipeline/services/ranker.py` | Candidate pair languages | Skip cross-language suggestions unless operator wants them |

**Wiring status.** Deferred. W2 wiring waits for pip-dep approval.

## 9 · Scheduled-updates job

None — detection is inline on ingest. Model file refresh is a manual
process when operators pull a new FastText release.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~15 MB (loaded model + inference state) | library docs |
| Disk | 126 MB (`lid.176.bin`) | FastText release |
| CPU | ~1 ms per call | FastText benchmark |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_detects_english` | Canonical path |
| `test_detects_japanese` | Multi-script |
| `test_short_text_returns_unknown` | Threshold |
| `test_low_confidence_returns_unknown` | Confidence floor |
| `test_empty_returns_empty_list` | Degenerate |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 detections | < 200 ms | > 2 s |
| medium | 10 000 detections | < 15 s | > 2 min |
| large | 1 000 000 detections | < 25 min | > 3 h |

## 13 · Edge cases & failure modes

- **Model file missing** → `RuntimeError` at app startup; operator
  downloads the model.
- **GPU-only environment** — FastText is CPU; no GPU path needed.
- **Code-switched text** (English paragraph with one Japanese
  sentence) — returns the dominant language. Per-sentence detection
  could be added if needed (future enhancement).
- **Constructed/made-up text** (Klingon, Esperanto) — returns best
  approximation with low confidence; threshold filters it.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC | Normalised input improves detection on mixed-composition scripts |

| Downstream | Reason |
|---|---|
| #15 PySBD | Some sentence-boundary rules are language-specific |
| #16 spaCy | en_core_web_sm only handles English; language router picks the right spaCy model |

## 15 · Governance checklist

- [ ] Approve `fasttext-langdetect` pip dep + 126 MB model download (blocker)
- [ ] `fasttext_langid.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (126 MB disk; 15 MB RAM)
- [ ] Helper module written
- [ ] Benchmark module written
- [ ] Test module written
- [ ] TPE search space declared
- [ ] Pipeline wired (W2)
