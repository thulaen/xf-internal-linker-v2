# Slice 1.6 — sidecars multi-stage Dockerfile.
#
# Stage 1: golang:1.25-alpine builds two static binaries — sidecars (the gRPC
# server hosting 40 internal services) and sidecars-healthcheck (Docker
# liveness probe).
# Stage 2: scratch ships only the two binaries. Final image targets < 35 MB.
#
# The sidecars binary co-hosts 40 Apache-pattern internal services under one
# shared resource budget (512 MB RAM, 1 GB storage, 7-day retention). Per
# ADR 0006 + services/sidecars/README.md.
#
# Build:  docker build -t xf-linker-sidecars:latest .
# Run:    docker compose up sidecars  (the compose entry mounts sidecars_sock + sidecars_data).

# --- Stage 1: build -------------------------------------------------------
FROM golang:1.25-alpine AS build

WORKDIR /src
# Cache the module download separately so unrelated source edits do not blow
# the dependency layer cache.
COPY go.mod go.sum* ./
RUN go mod download

COPY . .

# CGO disabled so the binary is fully static and runs on scratch.
# trimpath strips the build host path; -s -w drops the symbol table and DWARF
# debug info — saves a few MB.
RUN CGO_ENABLED=0 GOOS=linux \
    go build -trimpath -ldflags="-s -w" -o /out/sidecars ./cmd/sidecars && \
    CGO_ENABLED=0 GOOS=linux \
    go build -trimpath -ldflags="-s -w" -o /out/sidecars-healthcheck ./cmd/sidecars-healthcheck

# --- Stage 2: runtime -----------------------------------------------------
FROM scratch

# The scratch image has no /tmp and no nonroot user database. We rely on the
# docker-compose `user: "1000:1000"` and the sidecars_sock + sidecars_data
# volume mounts for socket-dir + storage-dir creation.
COPY --from=build /out/sidecars /sidecars
COPY --from=build /out/sidecars-healthcheck /sidecars-healthcheck
# The binary reads services.manifest.yaml (default path, relative to cwd "/")
# at boot to learn the 40 services' priorities/budgets. The scratch image has
# no other files, so ship the manifest alongside the binary; without it the
# server fails "manifest load failed" and restart-loops. docker-compose may
# bind-mount a live copy over XF_SIDECARS_MANIFEST to override this baked one.
COPY --from=build /src/services.manifest.yaml /services.manifest.yaml

# GOMEMLIMIT enforces the 512 MB RAM cap from services.manifest.yaml at the
# runtime level. internal/shared/budget mirrors this with debug.SetMemoryLimit.
ENV GOMEMLIMIT=512MiB

# Expose nothing — the only listener is /var/run/xf/sidecars.sock, mounted in
# via the sidecars_sock named volume.

ENTRYPOINT ["/sidecars"]
