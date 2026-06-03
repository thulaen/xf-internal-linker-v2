FROM golang:1.25-bookworm AS go-tools

# Slice 1.5 — added staticcheck, buf, protoc-gen-go, and protoc-gen-go-grpc
# alongside the existing go-mutesting / golangci-lint / gosec install so the
# Go quality chain (scripts/run-go-*.sh) and the streamd binary promotion
# (services/streamd/cmd/streamd/main.go) both have what they need.
#
# protoc-gen-go and protoc-gen-go-grpc are version-pinned because generated
# protobuf code is committed to the repo; bumping the generator requires a
# stub-regeneration step that must be reviewed.
RUN go install github.com/avito-tech/go-mutesting/cmd/go-mutesting@latest && \
    go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.12.2 && \
    go install github.com/securego/gosec/v2/cmd/gosec@latest && \
    go install honnef.co/go/tools/cmd/staticcheck@latest && \
    go install github.com/bufbuild/buf/cmd/buf@latest && \
    go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.2 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1

FROM ubuntu:24.04

ENV PATH="/usr/local/go/bin:${PATH}"
ARG INFER_VERSION=1.2.0

COPY --from=go-tools /usr/local/go /usr/local/go
COPY --from=go-tools /go/bin/go-mutesting /usr/local/bin/go-mutesting
COPY --from=go-tools /go/bin/golangci-lint /usr/local/bin/golangci-lint
COPY --from=go-tools /go/bin/gosec /usr/local/bin/gosec
# Slice 1.5 — copy the four new Go binaries from the build stage.
COPY --from=go-tools /go/bin/staticcheck /usr/local/bin/staticcheck
COPY --from=go-tools /go/bin/buf /usr/local/bin/buf
COPY --from=go-tools /go/bin/protoc-gen-go /usr/local/bin/protoc-gen-go
COPY --from=go-tools /go/bin/protoc-gen-go-grpc /usr/local/bin/protoc-gen-go-grpc

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      cmake \
      ninja-build \
      build-essential \
      icecc \
      libtbb-dev \
      clang-19 \
      clang-format-19 \
      clang-tidy-19 \
      llvm-19 \
      libclang-rt-19-dev \
      cppcheck \
      iwyu \
      lcov \
      xz-utils \
      bc \
      protobuf-compiler \
      python3 \
      python3-dev \
      python3-pip \
      python-is-python3 \
      libgmp-dev && \
    curl -1sLf 'https://dl.cloudsmith.io/public/mull-project/mull-stable/setup.deb.sh' | bash && \
    apt-get update && \
    apt-get install -y --no-install-recommends mull-19 && \
    curl -sSL "https://github.com/facebook/infer/releases/download/v${INFER_VERSION}/infer-linux-x86_64-v${INFER_VERSION}.tar.xz" \
      | tar -C /opt -xJ && \
    ln -s "/opt/infer-linux-x86_64-v${INFER_VERSION}/bin/infer" /usr/local/bin/infer && \
    pip install --break-system-packages --ignore-installed --no-cache-dir mutmut==3.5.0 pybind11==2.13.6 semgrep && \
    rm -rf /var/lib/apt/lists/*

# Install Rust toolchain via rustup (stable channel).
# cargo-mutants provides mutation testing for Rust code.
# cargo-fuzz provides libFuzzer-backed fuzz testing; the "|| true" allows the
# build to succeed on architectures where nightly is unavailable for fuzzing.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable && \
    . "$HOME/.cargo/env" && \
    cargo install cargo-mutants && \
    (cargo install cargo-fuzz --version "^0.12" || true) && \
    rm -rf /root/.cargo/registry /root/.cargo/git

ENV PATH="/root/.cargo/bin:${PATH}"

# Install GHC and cabal via ghcup (non-interactive, no Stack).
# hlint is the standard Haskell linter used by the quality chain.
RUN curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | \
      BOOTSTRAP_HASKELL_NONINTERACTIVE=1 BOOTSTRAP_HASKELL_INSTALL_NO_STACK=1 sh && \
    . "$HOME/.ghcup/env" && \
    cabal update && \
    cabal install hlint && \
    rm -rf /root/.cabal/packages /root/.cabal/logs

ENV PATH="/root/.ghcup/bin:/root/.cabal/bin:${PATH}"

WORKDIR /repo

CMD ["bash", "-lc", "mutmut --version && mull-runner-19 --version && go version && command -v go-mutesting >/dev/null && golangci-lint --version && gosec -version && staticcheck -version && buf --version && protoc --version && protoc-gen-go --version && cmake --version && clang++-19 --version && clang-tidy-19 --version && cppcheck --version && include-what-you-use --version && infer --version && semgrep --version && rustc --version && cargo --version && cargo mutants --version && ghc --version && cabal --version && hlint --version && echo 'compiled tools ready'"]
