import time
import numpy as np
import scoring
import simsearch
import l2norm


def bench_scoring():
    print("\n--- Benchmarking Scoring ---")
    n_rows = 100000
    k_components = 8

    component_scores = np.random.rand(n_rows, k_components).astype(np.float32)
    weights = np.random.rand(k_components).astype(np.float32)
    silo = np.random.rand(n_rows).astype(np.float32)

    # Warmup
    _ = scoring.calculate_composite_scores_full_batch(component_scores, weights, silo)

    start = time.perf_counter()
    for _ in range(100):
        _ = scoring.calculate_composite_scores_full_batch(
            component_scores, weights, silo
        )
    end = time.perf_counter()

    avg_ms = (end - start) * 1000 / 100
    print(f"Scoring (100k rows, 8 components) avg time: {avg_ms:.4f} ms")


def bench_simsearch():
    print("\n--- Benchmarking SimSearch ---")
    dimension = 384
    num_sentences = 50000
    num_candidates = 5000
    top_k = 100

    destination = np.random.rand(dimension).astype(np.float32)
    sentences = np.random.rand(num_sentences, dimension).astype(np.float32)
    candidate_rows = np.random.choice(
        num_sentences, num_candidates, replace=False
    ).astype(np.int32)

    # Warmup
    _ = simsearch.score_and_topk(destination, sentences, candidate_rows, top_k)

    start = time.perf_counter()
    for _ in range(50):
        _ = simsearch.score_and_topk(destination, sentences, candidate_rows, top_k)
    end = time.perf_counter()

    avg_ms = (end - start) * 1000 / 50
    print(f"SimSearch (50k total, 5k candidates, dim 384) avg time: {avg_ms:.4f} ms")


def bench_l2norm():
    print("\n--- Benchmarking L2Norm ---")
    rows = 10000
    cols = 384
    data = np.random.rand(rows, cols).astype(np.float32)

    # Warmup
    l2norm.normalize_l2_batch(data.copy())

    start = time.perf_counter()
    for _ in range(100):
        l2norm.normalize_l2_batch(data.copy())
    end = time.perf_counter()

    avg_ms = (end - start) * 1000 / 100
    print(f"L2Norm (10k x 384) avg time: {avg_ms:.4f} ms")


if __name__ == "__main__":
    bench_scoring()
    bench_simsearch()
    bench_l2norm()
