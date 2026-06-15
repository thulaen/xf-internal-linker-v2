use advanced_graph_signals::evaluate_advanced_graph_signals_core;
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};

/// One batch of per-candidate inputs for the 6 advanced graph signals.
struct BenchInputs {
    spectral_scores: Vec<f64>,
    tosd_filter_strength: f64,
    transition_counts: Vec<i32>,
    out_degrees: Vec<i32>,
    dstp_smoothing_alpha: f64,
    local_degrees: Vec<i32>,
    global_degrees: Vec<i32>,
    block_probabilities: Vec<f64>,
    flat_distances: Vec<f64>,
    density_gradients: Vec<f64>,
    rgsd_curvature_penalty: f64,
    is_cross_silo: Vec<u8>,
    persona_matches: Vec<f64>,
    csbr_min_overlap_threshold: f64,
}

fn generate_data(size: usize) -> BenchInputs {
    BenchInputs {
        spectral_scores: vec![2.0; size],
        tosd_filter_strength: 0.8,
        transition_counts: vec![5; size],
        out_degrees: vec![10; size],
        dstp_smoothing_alpha: 5.0,
        local_degrees: vec![5; size],
        global_degrees: vec![20; size],
        block_probabilities: vec![0.75; size],
        flat_distances: vec![0.2; size],
        density_gradients: vec![1.0; size],
        rgsd_curvature_penalty: 1.5,
        is_cross_silo: vec![1; size],
        persona_matches: vec![0.85; size],
        csbr_min_overlap_threshold: 0.7,
    }
}

fn bench_signals(c: &mut Criterion) {
    let mut group = c.benchmark_group("advanced_graph_signals");

    for &size in &[10usize, 100, 500] {
        group.bench_with_input(BenchmarkId::from_parameter(size), &size, |b, &size| {
            let d = generate_data(size);
            b.iter(|| {
                evaluate_advanced_graph_signals_core(
                    black_box(&d.spectral_scores),
                    black_box(d.tosd_filter_strength),
                    black_box(&d.transition_counts),
                    black_box(&d.out_degrees),
                    black_box(d.dstp_smoothing_alpha),
                    black_box(&d.local_degrees),
                    black_box(&d.global_degrees),
                    black_box(&d.block_probabilities),
                    black_box(&d.flat_distances),
                    black_box(&d.density_gradients),
                    black_box(d.rgsd_curvature_penalty),
                    black_box(&d.is_cross_silo),
                    black_box(&d.persona_matches),
                    black_box(d.csbr_min_overlap_threshold),
                )
            });
        });
    }
    group.finish();
}

criterion_group!(benches, bench_signals);
criterion_main!(benches);
