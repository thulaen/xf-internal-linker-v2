# ─────────────────────────────────────────────────────────────────
# XF Internal Linker V2 — Django Backend Dockerfile
# Python 3.12 (NOT 3.13 — ML libraries lag behind latest Python)
# ─────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for ML libraries and PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    git \
    curl \
    libtbb-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -c "import drf_spectacular"

# Download spaCy language model
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY . .
 
# Build C++ extensions
RUN cd extensions && python setup.py build_ext --inplace

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
