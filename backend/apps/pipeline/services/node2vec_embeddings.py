"""Node2Vec graph embeddings — pick #37.

Reference
---------
Grover, A. & Leskovec, J. (2016). "node2vec: Scalable Feature Learning
for Networks." *Proceedings of the 22nd ACM SIGKDD Conference*,
pp. 855-864.

Goal
----
Produce dense vector embeddings for every node in a graph by running
biased random walks and feeding them through Word2Vec. The walks'
``p`` and ``q`` parameters trade off BFS-vs-DFS bias, letting the
embeddings capture either community structure (when q > 1) or
structural equivalence (when p > 1).

For the linker: feed the inter-content-item graph (edges = links)
to Node2Vec; the resulting per-content-item vector becomes a feature
for the ranker — destinations whose graph neighbourhood looks like
the host's graph neighbourhood get a relevance bump.

Wraps the ``node2vec`` PyPI package (which itself wraps ``networkx``
and ``gensim.Word2Vec``). Cold-start safe: missing pip deps →
:func:`load_embeddings` returns ``{}``; trainer is a no-op.
"""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass
from pathlib import Path

try:
    import networkx as _nx
    from node2vec import Node2Vec as _Node2Vec

    HAS_NODE2VEC = True
except ImportError:  # pragma: no cover — depends on pip env
    _nx = None  # type: ignore[assignment]
    _Node2Vec = None  # type: ignore[assignment]
    HAS_NODE2VEC = False


logger = logging.getLogger(__name__)


KEY_EMBEDDINGS_PATH = "node2vec.embeddings_path"
KEY_DIMENSION = "node2vec.dimension"
DEFAULT_DIMENSION: int = 64

# Storage: Parquet sidecar at the configured path. The pickle format remains
# readable for back-compatibility, but every fresh fit_and_save() writes Parquet.
# After the first weekly retrain post-deploy the legacy pickle file becomes
# orphaned; a future session can delete the pickle code path entirely.
_PARQUET_SUFFIX = ".parquet"

#: Grover & Leskovec §4 default — walk length and p/q values from
#: the paper's Table 1 setup.
DEFAULT_WALK_LENGTH: int = 30
DEFAULT_NUM_WALKS: int = 200
DEFAULT_P: float = 1.0
DEFAULT_Q: float = 1.0
DEFAULT_WINDOW: int = 10


@dataclass(frozen=True)
class Node2VecEmbeddings:
    """Per-node embedding map + the dimension."""

    vectors: dict[str, list[float]]
    dimension: int

    @property
    def is_empty(self) -> bool:
        return not self.vectors


_EMPTY = Node2VecEmbeddings(vectors={}, dimension=0)
_CACHE: tuple[str, Node2VecEmbeddings] | None = None


def is_available() -> bool:
    """True when the Node2Vec stack is importable."""
    return HAS_NODE2VEC


def _read_path() -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=KEY_EMBEDDINGS_PATH).first()
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
        return ""
    return (row.value if row else "") or ""


def _parquet_companion_path(path: str) -> str:
    """Return the Parquet sidecar path for a configured embeddings location.

    Maps ``embeddings.pkl`` → ``embeddings.parquet`` so the AppSetting can
    keep pointing at the historical pickle path while we transparently
    migrate the on-disk format.
    """
    p = Path(path)
    if p.suffix.lower() == _PARQUET_SUFFIX:
        return str(p)
    return str(p.with_suffix(_PARQUET_SUFFIX))


def _load_parquet(path: str) -> Node2VecEmbeddings | None:
    """Read a Parquet snapshot if present; return None on absence/failure."""
    if not os.path.exists(path):
        return None
    try:
        import polars as pl

        df = pl.read_parquet(path)
        vectors = {str(node): [float(x) for x in vec] for node, vec in df.iter_rows()}
        if not vectors:
            return _EMPTY
        dimension = len(next(iter(vectors.values())))
        return Node2VecEmbeddings(vectors=vectors, dimension=int(dimension))
    except Exception as exc:  # noqa: BLE001 — Parquet read failure falls back to legacy pickle below.
        logger.warning("node2vec_embeddings: Parquet load failed at %s: %s", path, exc)
        return None


def load_embeddings() -> Node2VecEmbeddings:
    """Return cached or newly-loaded Node2Vec vectors.

    Reads the Parquet sidecar first; falls back to the legacy pickle file
    (still on disk for one weekly retrain after the upgrade) if Parquet is
    missing. Cold-start safe: missing pip deps / missing path / missing file
    → :data:`_EMPTY`.
    """
    global _CACHE
    if not HAS_NODE2VEC:
        return _EMPTY
    path = _read_path()
    if not path:
        return _EMPTY
    if _CACHE is not None and _CACHE[0] == path:
        return _CACHE[1]

    parquet_path = _parquet_companion_path(path)
    parquet_payload = _load_parquet(parquet_path)
    if parquet_payload is not None:
        _CACHE = (path, parquet_payload)
        return parquet_payload

    if not os.path.exists(path):
        return _EMPTY
    try:
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
    except Exception as exc:
        logger.warning("node2vec_embeddings: pickle load failed: %s", exc)
        return _EMPTY
    if not isinstance(payload, dict) or "vectors" not in payload:
        return _EMPTY
    out = Node2VecEmbeddings(
        vectors=dict(payload["vectors"]),
        dimension=int(payload.get("dimension", DEFAULT_DIMENSION)),
    )
    _CACHE = (path, out)
    return out


def vector_for(node_id) -> list[float] | None:
    """Return the embedding for *node_id* or ``None`` on cold start.

    Honours the ``node2vec.enabled`` AppSetting toggle (cached via
    :mod:`apps.core.runtime_flags`); when off, returns ``None`` even
    if a real model is loaded.
    """
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("node2vec.enabled", default=True):
        return None
    emb = load_embeddings()
    if emb.is_empty:
        return None
    return emb.vectors.get(str(node_id))


def _build_graph_from_edges(edges: list[tuple]):
    """Construct an undirected weighted graph from the (src, dst, [weight]) tuples."""
    graph = _nx.Graph()
    for edge in edges:
        if len(edge) == 3:
            graph.add_edge(edge[0], edge[1], weight=float(edge[2]))
        elif len(edge) == 2:
            graph.add_edge(edge[0], edge[1])
    return graph


def _train_node2vec(graph, *, dimension, walk_length, num_walks, p, q, window):
    """Run Node2Vec training and extract per-node vectors."""
    n2v = _Node2Vec(
        graph,
        dimensions=dimension,
        walk_length=walk_length,
        num_walks=num_walks,
        p=p,
        q=q,
        workers=1,
        quiet=True,
    )
    model = n2v.fit(window=window, min_count=1, batch_words=4)
    return {
        str(node): [float(x) for x in model.wv[str(node)]] for node in graph.nodes()
    }


def fit_and_save(
    edges: list[tuple],
    *,
    output_path: str,
    dimension: int = DEFAULT_DIMENSION,
    walk_length: int = DEFAULT_WALK_LENGTH,
    num_walks: int = DEFAULT_NUM_WALKS,
    p: float = DEFAULT_P,
    q: float = DEFAULT_Q,
    window: int = DEFAULT_WINDOW,
) -> bool:
    """Train Node2Vec on the supplied edge list and save to disk.

    *edges* is a list of ``(src, dst)`` or ``(src, dst, weight)`` tuples.
    Returns True on success, False on missing deps, degenerate graph, or
    training failures. Persists Parquet at the sibling ``.parquet`` path;
    falls back to pickle only if Polars is unavailable.
    """
    if not HAS_NODE2VEC:
        logger.info("node2vec_embeddings.fit_and_save: dep missing — skip")
        return False
    if not edges:
        return False
    try:
        graph = _build_graph_from_edges(edges)
        if graph.number_of_nodes() < 2:
            return False
        vectors = _train_node2vec(
            graph,
            dimension=dimension,
            walk_length=walk_length,
            num_walks=num_walks,
            p=p,
            q=q,
            window=window,
        )
    except Exception as exc:
        logger.warning("node2vec_embeddings.fit_and_save failed: %s", exc)
        return False
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    parquet_path = _parquet_companion_path(output_path)
    if not _save_parquet(parquet_path, vectors=vectors, dimension=dimension):
        with open(output_path, "wb") as fh:
            pickle.dump({"vectors": vectors, "dimension": dimension}, fh, protocol=4)
    global _CACHE
    _CACHE = None
    return True


def _save_parquet(path: str, *, vectors: dict[str, list[float]], dimension: int) -> bool:
    """Write Parquet atomically; return False if Polars or the helper is missing."""
    try:
        import polars as pl

        from apps.pipeline.services._parquet_io import write_parquet_atomic
    except ImportError:
        logger.debug("Polars or _parquet_io missing — falling back to pickle")
        return False
    try:
        node_ids = list(vectors.keys())
        vec_lists = [list(vectors[k]) for k in node_ids]
        df = pl.DataFrame(
            {"node_id": node_ids, "vector": vec_lists},
            schema={"node_id": pl.Utf8, "vector": pl.List(pl.Float32)},
        )
        write_parquet_atomic(df, path, estimated_bytes=max(1, len(node_ids)) * dimension * 5)
        return True
    except Exception as exc:  # noqa: BLE001 — Parquet write failed; caller falls back to pickle.
        logger.warning("node2vec_embeddings: Parquet write failed at %s: %s", path, exc)
        return False
