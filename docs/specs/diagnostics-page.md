# Diagnostics Page

## Summary

The Diagnostics page is the operator-facing health screen for this app. It shows
whether the local services are healthy, whether errors need action, and whether
ranking signals are producing real diagnostic data or safely falling back to
neutral values.

This Slice 2 extension adds a compact System Health card for each Wave-2 model:
FR-053 Passage-Level Relevance plus FR-099 through FR-105 graph-topology
signals. These cards do not change ranking. They only make existing signal
diagnostics easier to inspect.

## Academic Source

The cards reuse the already-approved source for each signal:

| Signal | Source |
|---|---|
| FR-053 Passage-Level Relevance | Patent US9940367B1, *Scoring Candidate Answer Passages*; Callan 1994, SIGIR passage-level evidence |
| FR-099 DARB | Page, Brin, Motwani & Winograd 1999, *The PageRank Citation Ranking*, Stanford InfoLab 1999-66 |
| FR-100 KMIG | Katz 1953, *Psychometrika* 18(1):39-43, DOI `10.1007/BF02289026` |
| FR-101 TAPB | Tarjan 1972, *SIAM Journal on Computing* 1(2):146-160, DOI `10.1137/0201010` |
| FR-102 KCIB | Seidman 1983, *Social Networks* 5(3):269-287, DOI `10.1016/0378-8733(83)90028-X` |
| FR-103 BERP | Hopcroft & Tarjan 1973, *Communications of the ACM* 16(6):372-378, DOI `10.1145/362248.362272` |
| FR-104 HGTE | Shannon 1948, *Bell System Technical Journal* 27(3):379-423, DOI `10.1002/j.1538-7305.1948.tb01338.x` |
| FR-105 RSQVA | Salton & Buckley 1988, *Information Processing & Management* 24(5):513-523, DOI `10.1016/0306-4573(88)90021-0` |

## Architecture Lane

Backend health aggregation lives in `backend/apps/diagnostics/`. It reads
recent `Suggestion` diagnostic JSON fields and returns a plain JSON summary
through the existing `/api/system/status/weights/` endpoint.

Frontend rendering lives in the existing `/diagnostics` component. It reuses
the existing "View spec" dialog so the operator can open the exact source spec
without leaving the page.

## Card Contract

Each Wave-2 card shows:

- signal name;
- last diagnostic timestamp;
- sample count over the last 7 days;
- neutral-fallback rate over the last 7 days;
- plain-English status;
- `View spec` action.

Neutral fallback means the signal safely produced its no-op value instead of
real evidence. For FR-099 through FR-105 this is
`fallback_triggered == true`. For FR-053 this is a
`passage_relevance_state` beginning with `neutral_`.

## Edge Cases

- No recent diagnostic blobs: show "No recent diagnostics" and no fallback
  percentage.
- Mixed real and neutral diagnostics: show the computed percentage.
- Missing spec path: hide or disable the spec action.
- Backend errors: the existing diagnostics error handling remains responsible
  for surfacing endpoint failures.

## Diagnostics

This page is itself the diagnostic surface. It lets the operator answer:

1. Did this signal run recently?
2. Is it mostly using real evidence or neutral fallback?
3. Which spec explains the signal?

## Gate Justifications

No new ranking signal, score formula, weight, migration, feature toggle, TPE
search-space entry, or per-content artifact table is introduced. The slice is a
read-only health surface over already-shipped `Suggestion` fields.

## Pending

- None for this slice.
