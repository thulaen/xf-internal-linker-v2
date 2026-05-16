# Slice 1.5 — streamd developer-side Makefile.
#
# Targets:
#   make build   — compile the streamd + healthcheck binaries
#   make test    — go test -race -shuffle=on -count=1 ./...
#   make bench   — run the speed benchmark (integration build tag)
#   make proto   — regenerate api/gen/*.pb.go from api.proto
#   make tidy    — go mod tidy + go mod download
#
# All targets assume the compiled-tools Docker image has the right toolchain.
# Run them inside the image:
#   docker compose run --rm compiled-tools make -C /repo/services/streamd <target>

GO          ?= go
PROTOC      ?= protoc
PROTO_FILE  := api.proto
GEN_DIR     := api/gen

.PHONY: build test bench proto tidy clean

build:
	$(GO) build -trimpath -o /tmp/streamd ./cmd/streamd
	$(GO) build -trimpath -o /tmp/streamd-healthcheck ./cmd/streamd-healthcheck

test:
	$(GO) test -race -shuffle=on -count=1 ./...

bench:
	$(GO) test -tags=integration -bench=BenchmarkPublishSubscribe -benchmem -count=3 -run='^$$' ./test/...

proto:
	mkdir -p $(GEN_DIR)
	$(PROTOC) --go_out=. --go-grpc_out=. \
		--go_opt=module=xf-internal-linker-v2/services/streamd \
		--go-grpc_opt=module=xf-internal-linker-v2/services/streamd \
		$(PROTO_FILE)

tidy:
	$(GO) mod tidy
	$(GO) mod download

clean:
	rm -f /tmp/streamd /tmp/streamd-healthcheck
