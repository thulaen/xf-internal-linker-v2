//! Criterion benchmark for the Rust `RankingDecisionEngine` scoring path.

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use ranking_decision_engine::{
    rank_candidates, CandidateInput, FeatureVector, MemoryBudget, RankingPolicy, WeightProfile,
};

fn make_candidates(count: usize) -> Vec<CandidateInput> {
    (0..count)
        .map(|idx| {
            let bucket = u8::try_from(idx % 100).unwrap_or(0);
            let value = f32::from(bucket) / 100.0;
            CandidateInput::new(
                format!("candidate-{idx}"),
                format!("destination-{idx}"),
                "host".to_string(),
                FeatureVector::new(value, 0.5, 0.5, 0.5),
            )
        })
        .collect()
}

fn bench_rank_candidates(c: &mut Criterion) {
    let profile = WeightProfile::new("bench".to_string(), 0.4, 0.25, 0.2, 0.15);
    let policy = RankingPolicy::new(20, MemoryBudget::default_2gb());

    for size in [10_usize, 100, 500] {
        let candidates = make_candidates(size);
        c.bench_function(&format!("rank_candidates_{size}"), |b| {
            b.iter(|| {
                rank_candidates(
                    black_box(candidates.clone()),
                    black_box(&profile),
                    black_box(&policy),
                )
                .expect("benchmark ranking should fit under memory budget")
            });
        });
    }
}

criterion_group!(benches, bench_rank_candidates);
criterion_main!(benches);
