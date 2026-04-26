"""Phase 6 optional-picks settings endpoint (Polish.A wiring).

Single REST view exposing the master-switch flag for each of the 10
Phase 6 optional helpers under one URL:
``/api/settings/phase6-picks/``.

Mirrors :mod:`apps.core.views_fr099_fr105` byte-for-byte in shape:
the frontend renders one card per pick but saves them together via
a single PUT. Backend persistence reuses the existing ``AppSetting``
table and the ``_persist_settings`` / ``_read_setting`` helpers
from ``views_antispam`` so the on-disk format matches every other
settings group.

Each pick has a single ``enabled`` boolean. The pip dep + model file
are baked into the production image; this endpoint only controls
whether the helper's per-call logic short-circuits via the AppSetting
flag. Defaults are seeded by migration 0043_seed_phase6_pick_defaults
to ``true`` so picks fire on real data out of the box; operators
flip individual picks off if a particular helper costs more than it
returns on their corpus.

Per pick:

- VADER #22         — Hutto & Gilbert 2014 ICWSM
- PySBD #15         — Sadvilkar & Neumann 2020 ACL Demos
- YAKE! #17         — Campos et al. 2020 Inf. Sci.
- Trafilatura #7    — Barbaresi 2021 ACL Demos
- FastText LangID #14 — Joulin et al. 2016 EACL
- LDA #18           — Blei, Ng, Jordan 2003 JMLR
- KenLM #23         — Heafield 2011 WMT
- Node2Vec #37      — Grover & Leskovec 2016 KDD
- BPR #38           — Rendle et al. 2009 UAI
- Factorization Machines #39 — Rendle 2010 ICDM
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.suggestions.recommended_weights import recommended_bool

from .views_antispam import _persist_settings, _read_setting


# ── Defaults + grouped config ────────────────────────────────────────


_PICK_DEFAULTS: dict[str, dict[str, object]] = {
    "vader_sentiment": {
        "enabled": recommended_bool("vader_sentiment.enabled"),
    },
    "pysbd_segmenter": {
        "enabled": recommended_bool("pysbd_segmenter.enabled"),
    },
    "yake_keywords": {
        "enabled": recommended_bool("yake_keywords.enabled"),
    },
    "trafilatura_extractor": {
        "enabled": recommended_bool("trafilatura_extractor.enabled"),
    },
    "fasttext_langid": {
        "enabled": recommended_bool("fasttext_langid.enabled"),
    },
    "lda": {
        "enabled": recommended_bool("lda.enabled"),
    },
    "kenlm": {
        "enabled": recommended_bool("kenlm.enabled"),
    },
    "node2vec": {
        "enabled": recommended_bool("node2vec.enabled"),
    },
    "bpr": {
        "enabled": recommended_bool("bpr.enabled"),
    },
    "factorization_machines": {
        "enabled": recommended_bool("factorization_machines.enabled"),
    },
}


_PICK_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "vader_sentiment": {
        "enabled": (
            "Pick #22 VADER sentiment master switch. Source: Hutto & "
            "Gilbert (2014) ICWSM. Rule-based 7,500-token polarity scorer."
        ),
    },
    "pysbd_segmenter": {
        "enabled": (
            "Pick #15 PySBD sentence-boundary master switch. Source: "
            "Sadvilkar & Neumann (2020) ACL Demos. Robust splitter for "
            "abbreviations, decimals, ellipses."
        ),
    },
    "yake_keywords": {
        "enabled": (
            "Pick #17 YAKE! keyword extractor master switch. Source: "
            "Campos et al. (2020) Inf. Sci. Unsupervised, language-"
            "agnostic n-gram scorer."
        ),
    },
    "trafilatura_extractor": {
        "enabled": (
            "Pick #7 Trafilatura main-content extractor master switch. "
            "Source: Barbaresi (2021) ACL Demos. Strips nav/footer/sidebar "
            "from HTML."
        ),
    },
    "fasttext_langid": {
        "enabled": (
            "Pick #14 FastText LangID master switch. Source: Joulin et al. "
            "(2016) EACL. 176-language detector via lid.176.bin (131 MB)."
        ),
    },
    "lda": {
        "enabled": (
            "Pick #18 LDA topic model master switch. Source: Blei, Ng & "
            "Jordan (2003) JMLR. Soft topic distribution per document via "
            "gensim."
        ),
    },
    "kenlm": {
        "enabled": (
            "Pick #23 KenLM trigram fluency master switch. Source: "
            "Heafield (2011) WMT. n-gram language-model scoring; trained "
            "weekly via lmplz."
        ),
    },
    "node2vec": {
        "enabled": (
            "Pick #37 Node2Vec graph-embedding master switch. Source: "
            "Grover & Leskovec (2016) KDD. Biased random-walk node "
            "embeddings via gensim Word2Vec."
        ),
    },
    "bpr": {
        "enabled": (
            "Pick #38 BPR (Bayesian Personalized Ranking) master switch. "
            "Source: Rendle et al. (2009) UAI. Pairwise LTR loss over "
            "approve/reject feedback via the implicit library."
        ),
    },
    "factorization_machines": {
        "enabled": (
            "Pick #39 Factorization Machines master switch. Source: "
            "Rendle (2010) ICDM. Linear + low-rank pairwise feature "
            "interactions; hand-rolled NumPy implementation."
        ),
    },
}


# ── Read / write helpers ─────────────────────────────────────────────


def get_phase6_pick_settings() -> dict[str, dict[str, bool]]:
    """Read the 10 ``<pick>.enabled`` AppSetting rows back as a tree."""
    result: dict[str, dict[str, bool]] = {}
    for pick, fields in _PICK_DEFAULTS.items():
        group: dict[str, bool] = {}
        for field, default in fields.items():
            key = f"{pick}.{field}"
            group[field] = _read_setting(
                key,
                default=bool(default),
                cast=lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
            )
        result[pick] = group
    return result


# ── Validation ───────────────────────────────────────────────────────


def _coerce_bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return fallback


def _validate_pick(pick: str, payload: dict, current: dict) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for field, default_value in _PICK_DEFAULTS[pick].items():
        incoming = payload.get(field, current.get(field, default_value))
        out[field] = _coerce_bool(incoming, bool(current.get(field, default_value)))
    return out


# ── DRF view ─────────────────────────────────────────────────────────


class Phase6PicksSettingsView(APIView):
    """GET/PUT for all 10 Phase 6 pick toggles in one request.

    Response shape::

        {
          "vader_sentiment":        {"enabled": true},
          "pysbd_segmenter":        {"enabled": true},
          "yake_keywords":          {"enabled": true},
          "trafilatura_extractor":  {"enabled": true},
          "fasttext_langid":        {"enabled": true},
          "lda":                    {"enabled": true},
          "kenlm":                  {"enabled": true},
          "node2vec":               {"enabled": true},
          "bpr":                    {"enabled": true},
          "factorization_machines": {"enabled": true}
        }

    PUT accepts the same shape (or any subset). Picks not in the
    payload keep their current value.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_phase6_pick_settings())

    def put(self, request):
        current = get_phase6_pick_settings()
        payload = request.data or {}
        validated: dict[str, dict[str, bool]] = {}
        for pick in _PICK_DEFAULTS:
            incoming = payload.get(pick) or {}
            validated[pick] = _validate_pick(pick, incoming, current[pick])

        from apps.core.runtime_flags import invalidate

        for pick, fields in validated.items():
            _persist_settings(
                pick,
                fields,
                category="ranking",
                descriptions=_PICK_DESCRIPTIONS[pick],
            )
            # Drop the cached flag so consumers see the new value on
            # their next call instead of waiting up to 60 s.
            for field in fields:
                invalidate(f"{pick}.{field}")
        return Response(validated)
