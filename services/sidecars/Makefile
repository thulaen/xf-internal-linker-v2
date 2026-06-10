# Slice 1.6 — sidecars developer-side Makefile.
#
# Targets:
#   make build   — compile sidecars + sidecars-healthcheck binaries
#   make test    — go test -race -shuffle=on -count=1 ./...
#   make bench   — run the 40 sub-benchmarks (one per internal service)
#   make proto   — regenerate api/gen/*.pb.go from api/*.proto
#   make tidy    — go mod tidy + go mod download
#
# All targets assume the compiled-tools Docker image has the right toolchain.
# Run them inside the image:
#   docker compose run --rm compiled-tools make -C /repo/services/sidecars <target>

GO          ?= go
PROTOC      ?= protoc
PROTO_DIR   := api
GEN_DIR     := api/gen

.PHONY: build test bench proto tidy clean

build:
	$(GO) build -trimpath -o /tmp/sidecars ./cmd/sidecars
	$(GO) build -trimpath -o /tmp/sidecars-healthcheck ./cmd/sidecars-healthcheck

test:
	$(GO) test -race -shuffle=on -count=1 ./...

bench:
	$(GO) test -bench=. -benchmem -count=1 -run='^$$' ./test/...

proto:
	mkdir -p $(GEN_DIR)
	$(PROTOC) --go_out=. --go-grpc_out=. \
		--go_opt=module=xf-internal-linker-v2/services/sidecars \
		--go-grpc_opt=module=xf-internal-linker-v2/services/sidecars \
		$(PROTO_DIR)/*.proto

tidy:
	$(GO) mod tidy
	$(GO) mod download

clean:
	rm -f /tmp/sidecars /tmp/sidecars-healthcheck
