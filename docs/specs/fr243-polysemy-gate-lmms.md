# FR-243 — Polysemy detection gate via WordNet sense counts

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Polysemy detection + diagnostic emission |
| **Settings prefix** | (constants in `polysemy_gate.py`; no operator tunables in v1) |
| **Pipeline stage** | Pre-Stage-1 host-sentence inspection |
| **Helper** | `apps.pipeline.services.polysemy_gate.detect_polysemous_terms`, `gate_polysemy`, `get_polysemy_status` |
| **Default state** | **ON.** Detector runs on every host sentence; when WordNet (NLTK corpus) is not installed (typical Docker container), the detector is a no-op and the diagnostic records `runtime_path = "no_wordnet"` so operators see why. |

## 2 · Motivation (ELI5)

"Apple" can mean a fruit OR the tech company. "Bank" can mean a place that holds money OR a riverbank. The pipeline's BGE-M3 model figures out which sense is meant from surrounding words — but if the surrounding context is short or weak, it can pick the wrong meaning. The fix is a *gate* that detects polysemous host sentences (those containing words with ≥2 WordNet senses) and emits a diagnostic so operators can see when this is happening. Future LMMS sense-vector picker (Loureiro & Jorge 2019) will route these sentences through a disambiguation step.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Loureiro, D. & Jorge, A. (2019). *Language Modelling Makes Sense: Propagating Representations through WordNet for Full-Coverage Word Sense Disambiguation* (LMMS). ACL 2019. arXiv:[1906.10007](https://arxiv.org/abs/1906.10007). State-of-the-art WordNet-based WSD. §4.2 — sense-separation cosine floor 0.3. |
| **Survey** | Bevilacqua, M. et al. (2021). *Recent Trends in Word Sense Disambiguation: A Survey.* IJCAI 2021. §2.1 — surface forms with ≥2 senses are polysemous. |
| **Lexical database** | Miller, G. A. (1995). *WordNet: A Lexical Database for English.* CACM 38(11). https://wordnet.princeton.edu/. |

## 4 · Output contract

`detect_polysemous_terms(text, *, min_polysemy=2, wordnet_module=None) -> list[str]`
- Returns the lower-cased surface forms with ≥`min_polysemy` WordNet senses.
- Cold-start safe: NLTK absent → empty list.

`gate_polysemy(host_sentence, ...) -> PolysemyDiagnostic`
- Frozen dataclass with `polysemous_terms`, `runtime_path` ("wordnet_lookup" or "no_wordnet"), `runtime_reason`.

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/services/polysemy_gate.py` | New file. ~150 lines. Pure-Python, optional NLTK. |
| `backend/apps/pipeline/tests_scaffolds.py::PolysemyGateTests` | 8 tests. |

## 6 · Test plan

8 SimpleTestCase tests:
1. **Threshold constant locked at 2** — Bevilacqua 2021 §2.1.
2. **No WordNet → empty list** (cold-start safe).
3. **Polysemous terms detected** — synthetic WordNet stand-in.
4. **Single-sense excluded** — below threshold.
5. **Empty text → empty result**.
6. **Gate returns diagnostic with `no_wordnet` path** when NLTK absent.
7. **Gate returns diagnostic with terms** when WordNet present.
8. **Status helper shape**.

## 7 · Wire-in (deferred)

The detector + diagnostic ship default-on. The next step is to attach
`PolysemyDiagnostic` to `SentenceSemanticMatch` so operators can filter
the review UI by polysemy hits. After that, a v2 commit will route
polysemous sentences through a sense-vector picker (Loureiro 2019 LMMS)
to actively disambiguate before retrieval.

## 8 · Citations on every default

- `MIN_POLYSEMY_THRESHOLD = 2` — Bevilacqua 2021 §2.1.
- `TOPICAL_CLUSTER_MIN_DISTANCE = 0.3` — Loureiro 2019 §4.2 (sense-separation floor; used by future LMMS picker).
- WordNet 3.1 as the lexical database — Miller 1995 (canonical English coverage).

## 9 · Status

Detector + diagnostic + tests + spec shipped 2026-05-07. LMMS sense-vector wire-in = v2.
