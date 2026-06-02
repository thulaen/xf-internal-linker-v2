# CPU-Only Paid Embeddings Runtime

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

[SPEC CITED: feature=cpu-paid-embeddings-runtime kind=technical_doc id=openai-embeddings verified_at=2026-05-28]
[SPEC CITED: feature=cpu-paid-embeddings-runtime kind=technical_doc id=gemini-embeddings verified_at=2026-05-28]
[SPEC CITED: feature=cpu-paid-embeddings-runtime kind=technical_doc id=pytorch-cpu-install verified_at=2026-05-28]
[SPEC CITED: feature=cpu-paid-embeddings-runtime kind=technical_doc id=faiss-cpu-package verified_at=2026-05-28]

## Purpose

The project no longer runs local GPU embedding or graph-ranking work. Embeddings
come from paid API providers, vector search uses CPU FAISS, and PageRank/HITS
use the existing CPU native kernel. Production code must not reintroduce CUDA,
CuPy, NVIDIA metrics, FAISS GPU packages, or Docker GPU flags.

## Sources Of Truth

- OpenAI embeddings guide: https://platform.openai.com/docs/guides/embeddings
- Gemini API embeddings guide: https://ai.google.dev/gemini-api/docs/embeddings
- PyTorch local install selector, CPU option: https://pytorch.org/get-started/locally/
- `faiss-cpu` package page: https://pypi.org/project/faiss-cpu/

OpenAI and Gemini expose embedding APIs over the network, so this codebase does
not need a local BGE-M3 model, CUDA tensor operations, or local VRAM management
to generate vectors. PyTorch documents CPU-only installation as a valid local
target when PyTorch is still needed elsewhere. FAISS publishes a CPU package, so
nearest-neighbor search does not require the GPU package.

## Behavior

Given the embedding provider is not configured, when the backend resolves a
provider, then it defaults to a paid API provider rather than local BGE-M3.

Given FAISS is installed, when the index is built, then it builds a CPU index
only and reports `device="CPU"`.

Given PageRank, personalized PageRank, or HITS runs, when the graph step is
computed, then the CPU native kernel is called directly with no CuPy dispatcher.

Given production code is scanned, when forbidden GPU terms are checked, then no
production file contains CUDA, CuPy, NVIDIA metrics, FAISS GPU, NVIDIA Docker
image, or Docker `--gpus=all` references.

## Requirements

### CPU-1 — Paid embedding providers only

The provider registry allows only configured paid API providers. Unknown values
raise a provider configuration error instead of falling back to local BGE-M3.

### CPU-2 — CPU FAISS only

`backend/requirements.txt` depends on `faiss-cpu`, not `faiss-gpu-cu12`, and
the FAISS index builder never calls GPU FAISS APIs.

### CPU-3 — No CuPy PageRank path

PageRank, personalized PageRank, and HITS do not import or dispatch through
CuPy. The CPU native kernel remains the single implementation.

### CPU-4 — No NVIDIA metrics or GPU UI/API fields

Runtime metrics, health endpoints, embedding status, and Angular views expose
CPU/RAM/system health only. They do not expose CUDA availability, VRAM, NVIDIA
temperature, or GPU utilization fields.

### CPU-5 — Permanent production-code guard

A Django `SimpleTestCase` scans production paths and fails if CUDA, CuPy,
`pynvml`, `faiss-gpu`, `nvidia/cuda`, or Docker `--gpus=all` references appear
outside ignored docs/tests/generated/build/cache paths.

## Out Of Scope

- Uninstalling the Windows NVIDIA driver.
- Rebuilding existing embedding vectors.
- Removing unrelated PyTorch CPU use if a non-GPU feature still needs it.
- Deleting historical docs that describe the old GPU implementation.

## Acceptance

- The no-GPU production guard passes.
- The focused embedding-provider tests pass with paid providers only.
- The FAISS, PageRank, health, runtime, and frontend tests touched by this
  cleanup pass.
