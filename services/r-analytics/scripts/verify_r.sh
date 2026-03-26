# ─────────────────────────────────────────────────────────────────
# R Analytics Service - Local Verification
# ─────────────────────────────────────────────────────────────────

# Build the R environment
docker build -t xf-linker-r-analytics ./services/r-analytics

# Run tests
docker run --rm xf-linker-r-analytics

# Run dashboard (if needed)
# docker run --rm -p 3838:3838 xf-linker-r-analytics Rscript -e "shiny::runApp('dashboard', host='0.0.0.0', port=3838)"
