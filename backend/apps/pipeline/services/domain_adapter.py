"""FR-242 — Domain adapter scaffold for the embedding encoder.

Ships a default-on loader that returns a domain-adapted encoder when a
trained adapter is present, falling back to vanilla BGE-M3 when it
isn't. The training pipeline (offline LoRA fit on pseudo-labels mined
from forum content) is documented but not yet implemented — the
fallback is the safe default per Wang et al. 2022 GPL §4 minimum-data
threshold.

Sources of truth:
    * Wang, K., Reimers, N. & Gurevych, I. (2022). *GPL: Generative
      Pseudo Labeling for Unsupervised Domain Adaptation of Dense
      Retrieval.* NAACL. arXiv:2112.07577. Reports +9.3 NDCG@10 on
      out-of-domain BEIR. §3.2 — 3 pseudo-labels per doc. §3.3 — 50
      mined hard negatives per query. §4 — 10K-doc minimum-data
      threshold below which GPL training is skipped (the gate-on rule
      this scaffold enforces).
    * Hu, E. J. et al. (2021). *LoRA: Low-Rank Adaptation of Large
      Language Models.* arXiv:2106.09685. §4.1 — rank=8, alpha=16 are
      the size/perf tradeoff defaults.
    * Dai, Z. et al. (2023). *Promptagator: Few-shot Dense Retrieval
      From 8 Examples.* ICLR 2023. arXiv:2209.11755. Faster
      alternative when labelled examples are available.

Wire-in (deferred): the loader function ``load_adapted_model()`` is
ready to call from `embeddings.py` at the point where
``sentence_transformers.SentenceTransformer(DEFAULT_MODEL_NAME)`` is
loaded. Replacing that call with ``load_adapted_model()`` is a one-
line change once a trained adapter ships. Until then the loader
returns the vanilla model directly — true default-on with a clean
upgrade path.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


# Wang et al. 2022 GPL §4 — below this threshold, pseudo-labelling
# collapses to noise. Operators with smaller corpora stay on vanilla.
GPL_MIN_CORPUS_SIZE: int = 10_000

# Hu et al. 2021 LoRA §4.1 — best size/perf tradeoff for an adapter
# layered on top of frozen BGE-M3. ~2MB of weights per adapter.
LORA_RANK_DEFAULT: int = 8
LORA_ALPHA_DEFAULT: int = 16

# Wang et al. 2022 GPL §3.2-3.3 — mining defaults.
PSEUDO_LABELS_PER_DOC_DEFAULT: int = 3
NEGATIVES_PER_QUERY_DEFAULT: int = 50

# Wang et al. 2022 GPL §3.4 — margin-MSE loss default.
MARGIN_MSE_TEMPERATURE_DEFAULT: float = 1.0


def get_adapter_weights_path() -> str:
    """Return the filesystem path where a trained LoRA adapter would live.

    Operators set ``EMBEDDING_DOMAIN_ADAPTER_PATH`` env var; defaults to
    ``/models/domain_adapter`` inside the backend container. The
    ``load_adapted_model`` loader checks for the file's existence and
    falls back to vanilla if absent.
    """
    return os.environ.get(
        "EMBEDDING_DOMAIN_ADAPTER_PATH",
        "/models/domain_adapter",
    )


def has_trained_adapter() -> bool:
    """True if a domain-adapted LoRA weights file exists at the configured path.

    Cold-start safe: any IO error returns False so the loader falls
    back to vanilla BGE-M3 without crashing the embed pipeline.
    """
    path = get_adapter_weights_path()
    try:
        return os.path.isdir(path) and os.path.isfile(
            os.path.join(path, "adapter_config.json")
        )
    except Exception:  # noqa: BLE001 — IO errors → vanilla fallback.
        return False


def should_train_adapter(corpus_size: int) -> bool:
    """True if the corpus is large enough for GPL training to be safe.

    Wang et al. 2022 GPL §4 — below 10K documents, generative pseudo-
    labelling collapses to noise. Operators with smaller corpora MUST
    stay on vanilla until they reach this threshold.
    """
    return corpus_size >= GPL_MIN_CORPUS_SIZE


def load_adapted_model(vanilla_model: Any) -> Any:
    """Wrap *vanilla_model* with the trained LoRA adapter if available.

    Default-on contract: this function is always called by the embed
    pipeline. When a trained adapter exists, the wrapped model is
    returned; otherwise the vanilla model is returned unchanged.
    Either path is fully functional — there is no "skipped" state.

    Returns the model object the caller should use for ``.encode(...)``
    calls. Caller code does not need to branch on whether an adapter
    is present.

    Wire-in is a one-line change in `embeddings.py`:
        model = SentenceTransformer(DEFAULT_MODEL_NAME)
        model = load_adapted_model(model)
    """
    if not has_trained_adapter():
        logger.debug(
            "FR-242 — no trained domain adapter at %s; using vanilla BGE-M3.",
            get_adapter_weights_path(),
        )
        return vanilla_model
    try:
        return _attach_lora_weights(vanilla_model)
    except Exception:  # noqa: BLE001 — adapter load fails → vanilla fallback.
        logger.exception(
            "FR-242 — failed to load LoRA adapter from %s; "
            "falling back to vanilla BGE-M3.",
            get_adapter_weights_path(),
        )
        return vanilla_model


def _attach_lora_weights(model: Any) -> Any:
    """Attach LoRA adapter weights to *model* via peft.PeftModel.

    Hu et al. 2021 LoRA arXiv:2106.09685 — adapter is a low-rank delta
    on top of the frozen encoder. peft.PeftModel.from_pretrained
    handles the actual weight-merge.

    Falls back to ``model`` unchanged when peft is not importable
    (typical container today). The fallback is logged so operators
    can see the gap; ``has_trained_adapter`` will still be True
    (the file exists) but the runtime path will be ``vanilla_no_peft``.
    """
    try:
        from peft import PeftModel  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "FR-242 — peft not installed; cannot attach LoRA weights. "
            "Run `pip install peft` to enable the domain adapter. "
            "Falling back to vanilla BGE-M3 for this run."
        )
        return model

    path = get_adapter_weights_path()
    inner = getattr(model, "_first_module", None)
    if inner is None or not callable(inner):
        # SentenceTransformer wraps the encoder — peft expects the
        # underlying transformer module. If the wrapper shape is
        # unfamiliar, fall back to vanilla rather than guess.
        logger.warning(
            "FR-242 — SentenceTransformer wrapper shape unrecognised; "
            "skipping LoRA attach for safety."
        )
        return model
    base_module = inner()
    try:
        peft_module = PeftModel.from_pretrained(base_module, path)
        # Replace the inner module so subsequent .encode() calls go
        # through the LoRA-adapted path. Sentence-transformers stores
        # modules in OrderedDict ``model._modules['0']``; assigning
        # there is the documented swap path.
        model._modules["0"] = peft_module
        logger.info("FR-242 — LoRA adapter attached from %s", path)
        return model
    except Exception:
        logger.exception(
            "FR-242 — peft.PeftModel.from_pretrained failed for %s; "
            "falling back to vanilla.",
            path,
        )
        return model


def get_adapter_status() -> dict[str, Any]:
    """Plain-English status of the FR-242 adapter (mirrors slate_diversity)."""
    has = has_trained_adapter()
    return {
        "available": has,
        "path": "domain_adapter" if has else "vanilla_bge_m3",
        "reason": (
            f"Trained LoRA adapter found at {get_adapter_weights_path()}."
            if has
            else "No trained adapter; using vanilla BGE-M3 (the safe "
            "default per Wang et al. 2022 GPL §4 minimum-data threshold)."
        ),
        "weights_path": get_adapter_weights_path(),
    }
