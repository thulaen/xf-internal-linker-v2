# ─────────────────────────────────────────────────────────────────
# XF Internal Linker V2 — Django Backend Dockerfile
# Python 3.12 (NOT 3.13 — ML libraries lag behind latest Python)
# ─────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS runtime

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for ML libraries and PostgreSQL.
# The kenlm + lmplz pair (pick #23) needs cmake + boost + eigen3 +
# libbz2 + zlib for the source build; everything else in this list
# was already required.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    git \
    curl \
    ca-certificates \
    libtbb-dev \
    cmake \
    libboost-all-dev \
    libeigen3-dev \
    libbz2-dev \
    liblzma-dev \
    zlib1g-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (`gh`) — the `print_open_issues` management command shells
# `gh run list --status failure --limit 10` to emit
# `[CI FAILED RUNS READ: ...]` (one of the mandatory session-opening
# ritual markers in CLAUDE.md). Without `gh` the marker falls back to
# `[CI FAILED RUNS READ: skipped — gh unavailable]`, which keeps commits
# unblocked but means the `gh_ci` source bucket is permanently dry and
# every session substitutes 3 picks from the agent queue.
#
# Installing via the official Debian APT repo per
# https://cli.github.com/packages/ so the binary stays in sync with
# stable Debian package updates. The actual authentication token is
# passed in via the GH_TOKEN environment variable in docker-compose.yml
# (sourced from .env). Without a token, `gh` is installed but every
# `gh run list` call exits non-zero and the fallback marker is emitted.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Why ``postgresql-client``:
#   * Group L #91 (masterplan) — daily ``pg_dump`` snapshot to a local
#     ``backups/`` directory. The Celery task at
#     ``apps.core.tasks_backups.create_database_snapshot`` invokes
#     ``pg_dump`` as a subprocess against the postgres service.
#   * ~10 MB increment to the image vs the gain of a one-line
#     restorable backup (``pg_restore`` is in the same package).

WORKDIR /app

# ── Pick #23 KenLM (Heafield 2011 WMT) — both binaries + Python lib ──
# `pip install kenlm` from PyPI does not produce a working wheel on
# Python 3.12 (cmake build fails inside the wheel sandbox). Build from
# source instead — the same checkout gives both:
#   1. /usr/local/bin/lmplz (and friends) for the W1 `kenlm_retrain`
#      training job.
#   2. The Python `kenlm` module installed system-wide for inference
#      via apps.pipeline.services.kenlm_fluency.
# Source: kpu/kenlm@master, MIT licence. Adds ~80 MB to the image;
# absorbed in this layer.
RUN git clone --depth=1 https://github.com/kpu/kenlm.git /tmp/kenlm \
    && mkdir -p /tmp/kenlm/build \
    && cd /tmp/kenlm/build \
    && cmake .. \
    && make -j 4 \
    && cp bin/lmplz bin/build_binary bin/query bin/filter /usr/local/bin/ \
    && cd /tmp/kenlm \
    && pip install --no-cache-dir . \
    && cd / \
    && rm -rf /tmp/kenlm

# Install Python dependencies first (better layer caching).
# A.5 — explicit ``pip cache purge`` at the end of the install layer
# strips any stray wheels pip retained even with ``--no-cache-dir``
# (spaCy + downstream subprocess installs occasionally leave a few
# files behind). Saves ~50-100 MB on the final image.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -c "import drf_spectacular" && \
    pip cache purge

# Download spaCy language model. ``spacy download`` shells out to pip
# under the hood; ``--no-cache-dir`` here tells that inner call not
# to populate ~/.cache/pip when fetching the model wheel.
RUN python -m spacy download en_core_web_sm && \
    pip cache purge

# FR-243 — NLTK WordNet corpus for polysemy detection. Downloaded once
# at image build time to /usr/share/nltk_data so every container
# (backend, celery-worker, celery-beat) reads from the shared baked
# location and not from a per-user cache. The polysemy gate falls
# back gracefully if nltk_data is missing, so a future image rebuild
# without this RUN will simply log "no_wordnet" runtime path.
# Source: https://wordnet.princeton.edu/ (Princeton, free for any use).
ENV NLTK_DATA=/usr/share/nltk_data
RUN mkdir -p /usr/share/nltk_data && \
    python -m nltk.downloader -d /usr/share/nltk_data wordnet omw-1.4

RUN mkdir -p /opt/xf/compiled /tmp/xf-build

# ── Pick #14 FastText LangID model (Joulin et al. 2016 EACL) ─────
# Downloads the official lid.176.bin (126 MB, 176 languages) once at
# build time to /opt/models/lid.176.bin. We use /opt/models — NOT
# /app/models — because the dev/prod compose stack bind-mounts
# ./backend → /app, which hides anything baked into /app at image
# build time. Putting the model in /opt keeps it visible.
# AppSetting `fasttext_langid.model_path` is seeded to that location
# via the seed migration.
# Source: dl.fbaipublicfiles.com — Facebook AI Research, MIT licence.
RUN mkdir -p /opt/models \
    && curl -sSL -o /opt/models/lid.176.bin \
        https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin

# Copy application code
COPY . .
 
# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /opt/xf/compiled /tmp/xf-build
USER appuser

EXPOSE 8000

FROM runtime AS quality

USER root

# Mutation and static-quality tools stay out of the runtime image.
# Note: mutmut has been moved to the mutation-tools stage.

RUN pip install --no-cache-dir \
      ruff==0.8.6 \
      bandit==1.8.3 \
      pip-audit==2.7.3 \
      safety==3.6.2 \
      pylint==3.3.8 \
      mypy==1.13.0 \
      django-stubs==5.1.1 \
      djangorestframework-stubs==3.15.1 \
      coverage==7.6.10 \
      pytest==9.0.3 \
      pytest-cov==6.0.0 \
      pytest-django==4.9.0 \
      pytest-asyncio==1.3.0 \
      pytest-randomly==3.15.0 \
      pytest-benchmark==5.1.0 \
      hypothesis==6.115.5 && \
    pip cache purge

USER appuser

FROM quality AS mutation-tools

USER root
RUN pip install --no-cache-dir mutmut==3.5.0
USER appuser
