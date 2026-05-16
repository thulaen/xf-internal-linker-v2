# Module: pipeline

**Layer:** 2 (business).
**Status:** Stub — full detail lands in slice 6.
**Maps to today:** `backend/apps/pipeline/`, the C++ extensions under `backend/extensions/`, scoring services, candidate selection, re-ranking.

## Plain-English summary

The pipeline module owns the 3-stage ranking pipeline that picks where a destination should link from. Stage 1 picks candidate host sentences. Stage 2 scores them. Stage 3 re-ranks the top set using better criteria. The C++ extensions that make stage 2 and stage 3 fast live inside this module; the Python orchestration around them lives here too.

If a function is about choosing where a link goes, it belongs here.

## Public interface

`pipeline.api` exports the call surface that the suggestions module uses. Examples slated for slice 6:

- `Candidate`, `ScoredCandidate`, `RankedCandidate` (typed records)
- `run_pipeline(destination_id: int) -> list[RankedCandidate]`
- `score_candidate(candidate: Candidate) -> ScoredCandidate`
- `rerank(candidates: list[ScoredCandidate]) -> list[RankedCandidate]`
- `PipelineRun` (database row representing one run)

The C++ extensions are private. Their Python wrappers are exposed through `api.py` only.

## Job (the "and"-test)

Pipeline owns one job: **rank candidate host sentences for a destination.** It does not own how a suggestion is reviewed (`suggestions`), how analytics feed back into the score (`analytics` produces signals; `pipeline` consumes them through typed records), or how the link graph is stored (`graph`).

## Owned tables

- `PipelineRun`, `PipelineStage`
- `Candidate`, `ScoredCandidate`, `RankedCandidate`
- Scoring-cache tables (per `(content_hash, signal_version)`, per the no-duplicates rule)

The full list arrives with the slice-6 move.

## Dependencies

- `platform` (hardware profile, disk-pressure, audit logging)
- `content` (read posts, distilled text, anchor phrases)

Pipeline does **not** depend on `suggestions`, `analytics`, `graph`, `operations`, `governance`. It is a sibling of `suggestions`, `analytics`, and `graph` at Layer 2.

If `pipeline` needs analytics signals as inputs, the signals arrive as typed records on `analytics.api`. The pipeline reads from `analytics.api`, not the other way around.

## Open questions

- Where does the FAISS index sit — inside `pipeline` (close to the consumer) or in `platform` (cross-cutting)? Current lean: `pipeline`, because the index lifecycle is tightly coupled to scoring.
- Per the C++-first rule, every hot path goes through a C++ extension. Slice 6 confirms the Python wrapper is the only public surface, and the C++ shared library is built through the Docker-managed path.

## Citations

- US10700948B2 — architectural fitness functions for module-dependency enforcement (applicable to ranking pipelines).
- Sivic & Zisserman 2003 ICCV — inverted-file index used in stage-1 candidate selection.
- Jégou-Douze-Schmid 2010 CVPR — IVFADC (Asymmetric Distance Computation), used in pipeline scoring.

## Slice that moves this module

Slice 6. Lands after `platform`, `content`, `sources` because pipeline depends on all three.
