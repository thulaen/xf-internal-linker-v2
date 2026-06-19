# Compiled-tools image — Python + Rust ONLY (ADR 0007).
# `quality` stage: Rust toolchain (fmt/clippy/test/coverage/audit/deny/fuzz) plus
# the shared native build deps (cmake/clang/llvm) and the Python bindings tools
# (pybind11/maturin) + semgrep. `mutation-tools` stage adds mutmut + cargo-mutants.
# Go, C/C++, Haskell, and Lua tooling were removed with those languages.
FROM ubuntu:24.04 AS quality

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      cmake \
      ninja-build \
      build-essential \
      libtbb-dev \
      clang-19 \
      llvm-19 \
      lcov \
      xz-utils \
      bc \
      protobuf-compiler \
      python3 \
      python3-dev \
      python3-pip \
      python-is-python3 \
      libgmp-dev && \
    pip install --break-system-packages --ignore-installed --no-cache-dir pybind11==2.13.6 maturin==1.13.3 semgrep && \
    rm -rf /var/lib/apt/lists/*

# Install Rust toolchain via rustup (stable channel).
# cargo-mutants provides mutation testing for Rust code.
# cargo-fuzz provides libFuzzer-backed fuzz testing; the "|| true" allows the
# build to succeed on architectures where nightly is unavailable for fuzzing.
# cargo-llvm-cov measures line/branch coverage; it needs the llvm-tools-preview
# rustup component (it shells out to llvm-cov / llvm-profdata from that
# component). The component is added to the stable toolchain (used by
# scripts/run-rust-coverage.sh).
# cargo-audit (RustSec advisory scan) and cargo-deny (license/ban/advisory
# policy) back the security/license steps of the Rust mandate gate
# (.githooks/check_rust_mandate.py). Without them the gate cannot run those
# checks for real; it degrades to a warning, so installing them here is the
# primary fix.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable && \
    . "$HOME/.cargo/env" && \
    rustup component add llvm-tools-preview && \
    cargo install cargo-llvm-cov && \
    cargo install cargo-audit --locked && \
    cargo install cargo-deny --locked && \
    (cargo install cargo-fuzz --version "^0.12" || true) && \
    rm -rf /root/.cargo/registry /root/.cargo/git

ENV CARGO_HOME="/root/.cargo"
ENV PATH="/root/.cargo/bin:${PATH}"

# Fast Rust test/link/cache path (Dell-only by construction — this image only
# runs on the Dell helper):
#   - mold + clang: mold is the fast linker; clang is the driver that accepts
#     -fuse-ld=mold. Installed in their own layer so the expensive
#     rustup/cargo-install layer above stays cached.
#   - cargo-nextest: prebuilt pinned release binary (faster and more
#     reproducible than `cargo install`). NOTE: nextest does not run doctests;
#     the Bazel Rust quality target keeps a `cargo test --doc` step for that.
#   - sccache: prebuilt pinned release binary. The runner scripts set
#     RUSTC_WRAPPER=sccache and mount the xf_sccache named volume at runtime,
#     so compile caches survive `cargo clean` and the per-sync tree wipe.
ARG NEXTEST_VERSION=0.9.92
ARG SCCACHE_VERSION=0.8.2
RUN apt-get update && \
    apt-get install -y --no-install-recommends mold clang && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL "https://github.com/nextest-rs/nextest/releases/download/cargo-nextest-${NEXTEST_VERSION}/cargo-nextest-${NEXTEST_VERSION}-x86_64-unknown-linux-gnu.tar.gz" \
      | tar -xz -C "$CARGO_HOME/bin" cargo-nextest && \
    curl -fsSL "https://github.com/mozilla/sccache/releases/download/v${SCCACHE_VERSION}/sccache-v${SCCACHE_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
      | tar -xz -C "$CARGO_HOME/bin" --strip-components=1 "sccache-v${SCCACHE_VERSION}-x86_64-unknown-linux-musl/sccache" && \
    cargo nextest --version && mold --version && sccache --version

# Image-level cargo config: route linking through clang + mold for every cargo
# invocation in this image. Living in $CARGO_HOME keeps the repo's own .cargo
# untouched (one place, Dell-only).
RUN printf '%s\n' \
      '[target.x86_64-unknown-linux-gnu]' \
      'linker = "clang"' \
      'rustflags = ["-C", "link-arg=-fuse-ld=mold"]' \
      > "$CARGO_HOME/config.toml"

WORKDIR /repo

CMD ["bash", "-lc", "cmake --version && clang-19 --version && semgrep --version && rustc --version && cargo --version && cargo llvm-cov --version && cargo audit --version && cargo deny --version && cargo nextest --version && mold --version && sccache --version && maturin --version && echo 'compiled tools ready'"]

FROM quality AS mutation-tools

RUN pip install --break-system-packages --ignore-installed --no-cache-dir mutmut==3.5.0

RUN . "$HOME/.cargo/env" && \
    cargo install cargo-mutants && \
    rm -rf /root/.cargo/registry /root/.cargo/git

CMD ["bash", "-lc", "mutmut --version && cargo mutants --version && echo 'mutation tools ready'"]
