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
    except Exception:
        return ""
    return (row.value if row else "") or ""


def load_embeddings() -> Node2VecEmbeddings:
    """Return cached or newly-loaded Node2Vec vectors.

    Cold-start safe: missing pip deps / missing path / missing file
    → :data:`_EMPTY`. Real-data ready: train via :func:`fit_and_save`
    (called from the W1 ``node2vec_walks`` job), point the AppSetting
    path at the result, and inference auto-activates.
    """
    global _CACHE
    if not HAS_NODE2VEC:
        return _EMPTY
    path = _read_path()
    if not path or not os.path.exists(path):
        return _EMPTY
    if _CACHE is not None and _CACHE[0] == path:
        return _CACHE[1]
    try:
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
    except Exception as exc:
        logger.warning("node2vec_embeddings: load failed: %s", exc)
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

    *edges* is a list of ``(src, dst)`` or ``(src, dst, weight)``
    tuples. Returns True on success, False when:
    - The pip dep is missing.
    - The graph has fewer than 2 nodes (degenerate).
    - Training raises.

    The persisted format is a pickled dict ``{"vectors": {node: vec},
    "dimension": int}``. :func:`load_embeddings` reads exactly that.
    """
    if not HAS_NODE2VEC:
        logger.info("node2vec_embeddings.fit_and_save: dep missing — skip")
        return False
    if not edges:
        return False
    try:
        graph = _nx.Graph()
        for edge in edges:
            if len(edge) == 3:
                graph.add_edge(edge[0], edge[1], weight=float(edge[2]))
            elif len(edge) == 2:
                graph.add_edge(edge[0], edge[1])
            else:
                continue
        if graph.number_of_nodes() < 2:
            return False
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
        vectors = {
            str(node): [float(x) for x in model.wv[str(node)]]
            for node in graph.nodes()
        }
    except Exception as exc:
        logger.warning("node2vec_embeddings.fit_and_save failed: %s", exc)
        return False
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as fh:
        pickle.dump(
            {"vectors": vectors, "dimension": dimension}, fh, protocol=4
        )
    # Clear the cache so the next load picks up the fresh file.
    global _CACHE
    _CACHE = None
    return True
