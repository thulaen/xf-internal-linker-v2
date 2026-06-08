# ranking_decision_engine

Rust authority crate for the RankingDecisionEngine.

It exposes the live ranking decision surface as `extensions.ranking_decision_engine`
through PyO3 and maturin. Python prepares data and stores results; Rust owns
memory checks, bounded scoring, final ordering, profile validation, governance
verdicts, and explanation lookup.

The source-backed design lives in
`docs/specs/fr-ranking-decision-engine.md`.
