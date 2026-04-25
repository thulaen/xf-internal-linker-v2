"""KenLM fluency scoring — pick #23.

Reference
---------
Heafield, K. (2011). "KenLM: Faster and Smaller Language Model
Queries." *Proceedings of the Sixth Workshop on Statistical Machine
Translation*, pp. 187-197.

Goal
----
KenLM is a fast, memory-efficient n-gram language model. Given a
trained model, the helper returns a per-token log-probability score
under that LM — a strong proxy for "naturalness" / "fluency" of a
sentence. Used by the ranker to demote anchor candidates that read
poorly.

Wraps the ``kenlm`` PyPI package (which itself wraps Heafield's C++
KenLM library). The training side requires the ``lmplz`` binary
from KenLM; this module exposes the inference side. Cold-start
safe: missing pip dep / missing model file → :data:`NEUTRAL_SCORE`.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

try:
    import kenlm as _kenlm

    HAS_KENLM = True
except ImportError:  # pragma: no cover — depends on pip env
    _kenlm = None  # type: ignore[assignment]
    HAS_KENLM = False


logger = logging.getLogger(__name__)


KEY_MODEL_PATH = "kenlm.model_path"

#: Returned by :func:`score_fluency` when no model is loaded. ``0.0``
#: log-prob is "neutral" — neither demote nor reward — which keeps
#: the ranker stable on cold start.
NEUTRAL_SCORE: float = 0.0


@dataclass(frozen=True)
class FluencyScore:
    """One sentence's fluency under the LM.

    ``log_prob`` is the natural-log probability of the sentence under
    the model. Larger (less negative) = more fluent. ``per_token``
    is normalised by token count so different-length sentences are
    comparable.
    """

    log_prob: float
    per_token: float
    token_count: int


_NEUTRAL = FluencyScore(log_prob=NEUTRAL_SCORE, per_token=NEUTRAL_SCORE, token_count=0)
_MODEL_CACHE: tuple[str, object] | None = None


def is_available() -> bool:
    """True when ``kenlm`` is importable."""
    return HAS_KENLM


def _read_model_path() -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=KEY_MODEL_PATH).first()
    except Exception:
        return ""
    return (row.value if row else "") or ""


def load_model():
    """Return the cached KenLM model or load from disk.

    Returns ``None`` when:
    - The pip dep is missing.
    - The model-path AppSetting is empty.
    - The file at the path doesn't exist.
    - Loading raises (corrupt file, version mismatch, etc.).
    """
    global _MODEL_CACHE
    if not HAS_KENLM:
        return None
    path = _read_model_path()
    if not path or not os.path.exists(path):
        return None
    if _MODEL_CACHE is not None and _MODEL_CACHE[0] == path:
        return _MODEL_CACHE[1]
    try:
        model = _kenlm.Model(path)
    except Exception as exc:
        logger.warning("kenlm_fluency: load failed: %s", exc)
        return None
    _MODEL_CACHE = (path, model)
    return model


def score_fluency(sentence: str) -> FluencyScore:
    """Return the LM log-prob for *sentence*.

    Empty / whitespace-only input → neutral. Missing pip dep / model
    file → neutral. Operator-flipped-off toggle → neutral. Real-
    data ready: install ``kenlm`` + place a model file at
    ``AppSetting["kenlm.model_path"]``, and every call upgrades
    automatically.
    """
    if not sentence or not sentence.strip():
        return _NEUTRAL
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("kenlm.enabled", default=True):
        return _NEUTRAL
    model = load_model()
    if model is None:
        return _NEUTRAL
    try:
        # KenLM expects a string; it tokenises on whitespace internally.
        log_prob = float(model.score(sentence, bos=True, eos=True))
    except Exception as exc:
        logger.debug("kenlm_fluency: score failed: %s", exc)
        return _NEUTRAL
    tokens = sentence.split()
    n = max(1, len(tokens))
    return FluencyScore(
        log_prob=log_prob,
        per_token=log_prob / n,
        token_count=len(tokens),
    )


def perplexity(sentence: str) -> float:
    """Return the per-token perplexity of *sentence*.

    ``perplexity = exp(-per_token_log_prob)``. Lower = more fluent.
    Cold-start safe: returns ``inf`` when no model is available,
    making "no signal" obvious to the ranker (which must explicitly
    handle the inf case with a clamp / ignore rule).
    """
    score = score_fluency(sentence)
    if score is _NEUTRAL or score.token_count == 0:
        return math.inf
    return math.exp(-score.per_token)


# ── Producer (W1.4 wiring — lmplz subprocess) ────────────────────


def lmplz_available() -> bool:
    """True when the ``lmplz`` binary is on ``$PATH``.

    The Python ``kenlm`` package handles inference; training (`lmplz`)
    is a separate C++ tool from the same project. Operators install
    it via apt / homebrew / source build. Cold-start safe — returns
    False when shutil can't find it.
    """
    import shutil

    return shutil.which("lmplz") is not None


def fit_arpa_with_lmplz(
    corpus_lines: list[str],
    *,
    output_arpa_path: str,
    order: int = 3,
    discount_fallback: bool = True,
) -> bool:
    """Train an ARPA-format n-gram LM via the ``lmplz`` binary.

    *corpus_lines* is one sentence per element (tokenised on
    whitespace by ``lmplz`` itself). *order* sets the n-gram size
    (3 = trigram, the helper's default).

    Cold-start safe:
    - ``lmplz`` not on PATH → returns False (caller can choose
      :class:`DeferredPickError`).
    - Empty corpus / fewer than 100 lines → returns False (lmplz
      requires a meaningful sample to fit reliably; below that
      threshold the model is unstable).
    - Subprocess raises → logged, returns False, no partial file
      left behind.

    Real-data ready: install lmplz on PATH and the producer
    activates. The helper does not load the resulting ARPA back into
    a binary KenLM model — operators or a follow-up step can run
    ``build_binary`` if they want the binary format. The Python
    ``kenlm.Model`` constructor accepts ARPA directly so loading
    the trained model just works.
    """
    import logging
    import os
    import subprocess
    import tempfile

    log = logging.getLogger(__name__)

    if not lmplz_available():
        return False
    if not corpus_lines:
        return False
    if len(corpus_lines) < 100:
        log.info(
            "kenlm_fluency.fit_arpa_with_lmplz: %d corpus lines (<100) — skip",
            len(corpus_lines),
        )
        return False

    # Write the corpus to a temp file. lmplz reads from stdin or a
    # file; we use stdin so we don't have to clean up an extra path.
    os.makedirs(os.path.dirname(output_arpa_path) or ".", exist_ok=True)
    cmd = ["lmplz", "-o", str(order), "--text", "/dev/stdin"]
    if discount_fallback:
        # Most small corpora trip "warning: x of y n-grams have a zero
        # count" — discount_fallback handles that by smoothing instead
        # of erroring out.
        cmd.append("--discount_fallback")

    corpus_blob = ("\n".join(corpus_lines) + "\n").encode("utf-8")
    try:
        with open(output_arpa_path, "wb") as out_fh:
            result = subprocess.run(
                cmd,
                input=corpus_blob,
                stdout=out_fh,
                stderr=subprocess.PIPE,
                check=False,
                timeout=15 * 60,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("kenlm_fluency.fit_arpa_with_lmplz: subprocess failed: %s", exc)
        # Best-effort cleanup of partial output.
        try:
            os.remove(output_arpa_path)
        except OSError:
            pass
        return False

    if result.returncode != 0:
        log.warning(
            "kenlm_fluency.fit_arpa_with_lmplz: lmplz exit %d — stderr tail: %s",
            result.returncode,
            (result.stderr or b"")[-512:].decode("utf-8", errors="replace"),
        )
        try:
            os.remove(output_arpa_path)
        except OSError:
            pass
        return False

    # Reset the inference cache so the next score_fluency picks up
    # the fresh model.
    global _MODEL_CACHE
    _MODEL_CACHE = None
    return True
