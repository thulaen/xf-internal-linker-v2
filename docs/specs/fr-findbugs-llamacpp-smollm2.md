# FindBugs AI Model Removal

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

FindBugs uses the deterministic Rust `speccheck find-bugs` scanner as the
source of truth. The SmolLM2 advisory model path is removed. This means no
llama.cpp server, no SmolLM2 GGUF file, no FindBugs model Docker volume, no
Mint model server, and no scheduled model-advisory task. Django still imports
scanner-confirmed findings into AutoIssue.

## Sources Of Truth

- Hovemeyer and Pugh 2004, FindBugs bug-pattern catalog discipline,
  doi:10.1145/1052883.1052895.
- ISO/IEC/IEEE 29119-3:2021 for BDD-style test documentation.

## Runtime Contract

Given the backend image is built, when the image recipe is checked, then it does
not install llama.cpp, `llama-cli`, `llama-server`, or the SmolLM2 GGUF file.

Given Windows starts the Django backend or default Celery worker, when FindBugs
runs, then no `FINDBUGS_SMOLLM2_*` environment variable is needed and no
FindBugs model volume is mounted.

Given FindBugs runs after the AI model removal, when the deterministic scanner
finishes, then FindBugs writes a status artifact with `status="removed"` and
`reason="operator_removed_ai_model"` and does not file a missing-model health
issue.

Given `/find-bugs` loads, when model status is present, then the GUI can show
that the advisory model was intentionally removed while scanner findings still
flow through AutoIssue.

## Speed And Resource Rules

- No model download may happen during requests, tasks, image builds, or Mint
  helper startup.
- No `docker-compose.mint-findbugs.yml` file remains.
- No `findbugs_model_runtime` Docker volume remains on Windows or Mint.
- No `findbugs-model-advisory` schedule remains.
- Scanner findings continue through the compiled `speccheck find-bugs` path.

## Test Cases

Given docker-compose defines the backend, when the compose integrity test reads
the environment, then all `FINDBUGS_SMOLLM2_*` model settings are absent.

Given the backend Dockerfile is read, when the image recipe is checked, then it
does not contain the pinned llama.cpp release asset or SmolLM2 model URL.

Given the repository is read, when FindBugs model runtime wiring is checked,
then there is no Mint-only model Compose file and no model provision script.

Given the scanner-only smoke runs, when `run_findbugs_scan()` completes, then
it returns `status="ok"`, `model.status="removed"`, and an AutoIssue import
summary.

[SPEC CITED: feature=fr-findbugs-llamacpp-smollm2 kind=academic_paper id=doi:10.1145/1052883.1052895 verified_at=2026-06-02]
