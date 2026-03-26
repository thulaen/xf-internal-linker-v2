# ─────────────────────────────────────────────────────────────────
# XF Internal Linker V2 — R Analytics Service Dockerfile
# Provides the R runtime for data-driven ranking optimization
# ─────────────────────────────────────────────────────────────────

FROM rocker/r-ver:4.4.0

# Install system dependencies for RPostgres and DBI
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libssl-dev \
    libxml2-dev \
    libcurl4-openssl-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    libuv1-dev \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    libicu-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the DESCRIPTION file first to cache package installation
COPY DESCRIPTION .

# Install R dependencies
# We use a simple script to install from CRAN for this interim scaffold
RUN Rscript -e "install.packages(c('DBI', 'RPostgres', 'config', 'dplyr', 'tibble', 'rlang', 'shiny', 'testthat'), repos='https://cloud.r-project.org/')"

# Copy the rest of the project files
COPY . .

# Default command: run tests
CMD ["Rscript", "tests/run_tests.R"]
