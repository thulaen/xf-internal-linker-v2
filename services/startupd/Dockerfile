# Stage 1: build two static binaries — startupd (the HTTP server) and
# startupd-healthcheck (the Docker liveness probe, used because FROM scratch
# provides no shell, curl, or wget for HEALTHCHECK CMD-SHELL forms).
FROM golang:1.25-alpine AS build

WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
# CGO disabled so both binaries are fully static and run on scratch.
# -trimpath strips build-host paths; -s -w drops symbol table + DWARF.
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
        -o /out/startupd ./cmd/startupd && \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
        -o /out/startupd-healthcheck ./cmd/startupd-healthcheck

# Stage 2: runtime — scratch image ships only the two static binaries.
FROM scratch

COPY --from=build /out/startupd /startupd
COPY --from=build /out/startupd-healthcheck /startupd-healthcheck
ENTRYPOINT ["/startupd"]
