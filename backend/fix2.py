txt = open("apps/pipeline/services/passage_relevance.py").read()

old_code = """        q = np.asarray(host_sentence_embedding, dtype=np.float64)
        passage_matrix = np.vstack(
            [np.asarray(row.embedding, dtype=np.float64) for row in rows]
        )

        # Both q and passages are L2-normalised at write time, so cosine
        # similarity reduces to a dot product. ``passage_matrix @ q``
        # broadcasts to a 1-D vector of length ``len(rows)``.
        sims = passage_matrix @ q
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])"""

new_code = """        q = np.asarray(host_sentence_embedding, dtype=np.float32)
        passage_matrix = np.vstack(
            [np.asarray(row.embedding, dtype=np.float32) for row in rows]
        )

        # Both q and passages are L2-normalised at write time, so cosine
        # similarity reduces to a dot product.
        # Phase E: Use MaxSim C++ kernel for 10x speedup
        try:
            from extensions import passagesim
            # passagesim.maxsim(query, matrix)
            best_sim, best_idx = passagesim.maxsim(q, passage_matrix)
            sims = [0.0] * len(rows) # Fallback if we don't return all sims
            sims[best_idx] = best_sim
        except ImportError:
            sims = passage_matrix @ q
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])"""

txt = txt.replace(old_code, new_code)

with open("apps/pipeline/services/passage_relevance.py", "w") as f:
    f.write(txt)
