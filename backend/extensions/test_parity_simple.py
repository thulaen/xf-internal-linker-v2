import numpy as np
import scoring
import simsearch
import l2norm

def test_scoring_parity():
    print("Testing Scoring Parity...")
    n_rows = 100
    k_components = 8
    component_scores = np.random.rand(n_rows, k_components).astype(np.float32)
    weights = np.random.rand(k_components).astype(np.float32)
    silo = np.random.rand(n_rows).astype(np.float32)
    
    # Python reference
    py_results = np.zeros(n_rows, dtype=np.float32)
    for i in range(n_rows):
        total = silo[i]
        for j in range(k_components):
            total += component_scores[i, j] * weights[j]
        py_results[i] = total
        
    cpp_results = scoring.calculate_composite_scores_full_batch(component_scores, weights, silo)
    
    np.testing.assert_allclose(py_results, cpp_results, rtol=1e-5, atol=1e-5)
    print("Scoring Parity OK!")

def test_simsearch_parity():
    print("Testing SimSearch Parity...")
    dimension = 64
    num_sentences = 100
    num_candidates = 20
    top_k = 5
    
    destination = np.random.rand(dimension).astype(np.float32)
    sentences = np.random.rand(num_sentences, dimension).astype(np.float32)
    candidate_rows = np.random.choice(num_sentences, num_candidates, replace=False).astype(np.int32)
    
    # Python reference
    scores = []
    for row_idx in candidate_rows:
        scores.append(np.dot(sentences[row_idx], destination))
    
    # Get top-K indices relative to candidate list
    scores = np.array(scores)
    top_k_indices = np.argsort(scores)[-top_k:][::-1]
    py_indices = top_k_indices
    py_scores = scores[top_k_indices]
    
    cpp_indices, cpp_scores = simsearch.score_and_topk(destination, sentences, candidate_rows, top_k)
    
    np.testing.assert_array_equal(py_indices, cpp_indices)
    np.testing.assert_allclose(py_scores, cpp_scores, rtol=1e-5, atol=1e-5)
    print("SimSearch Parity OK!")

if __name__ == "__main__":
    try:
        test_scoring_parity()
        test_simsearch_parity()
        print("\nAll Parity Tests Passed!")
    except Exception as e:
        print(f"\nParity Test Failed: {e}")
        import traceback
        traceback.print_exc()
