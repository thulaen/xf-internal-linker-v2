# ─────────────────────────────────────────────────────────────────
# XF Internal Linker V2 — Django Backend Dockerfile
# Python 3.12 (NOT 3.13 — ML libraries lag behind latest Python)
# ─────────────────────────────────────────────────────────────────

FROM python:3.12-slim

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
    libtbb-dev \
    cmake \
    libboost-all-dev \
    libeigen3-dev \
    libbz2-dev \
    liblzma-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

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

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -c "import drf_spectacular"

# Download spaCy language model
RUN python -m spacy download en_core_web_sm

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
 
# Build C++ extensions
RUN cd extensions && python setup.py build_ext --inplace

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
