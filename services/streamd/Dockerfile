# Slice 1.5 — streamd multi-stage Dockerfile.
#
# Stage 1: golang:1.25-alpine builds two static binaries — streamd (the gRPC
# server) and streamd-healthcheck (Docker liveness probe).
# Stage 2: scratch ships only the two binaries. Final image targets < 25 MB
# (typical Go static binary for a service this small is 8-15 MB).
#
# Build:  docker build -t xf-linker-streamd:latest .
# Run:    docker compose up streamd  (the compose entry mounts streamd_sock).

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
    go build -trimpath -ldflags="-s -w" -o /out/streamd ./cmd/streamd && \
    CGO_ENABLED=0 GOOS=linux \
    go build -trimpath -ldflags="-s -w" -o /out/streamd-healthcheck ./cmd/streamd-healthcheck

# --- Stage 2: runtime -----------------------------------------------------
FROM scratch

# The scratch image has no /tmp and no nonroot user database. We rely on the
# docker-compose `user: "1000:1000"` and the streamd_sock volume mount for
# socket directory creation.
COPY --from=build /out/streamd /streamd
COPY --from=build /out/streamd-healthcheck /streamd-healthcheck

# Expose nothing — the only listener is /var/run/xf/streamd.sock, mounted in
# via the streamd_sock named volume.

ENTRYPOINT ["/streamd"]
