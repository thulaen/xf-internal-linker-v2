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

ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /repo

CMD ["bash", "-lc", "cmake --version && clang-19 --version && semgrep --version && rustc --version && cargo --version && cargo llvm-cov --version && cargo audit --version && cargo deny --version && maturin --version && echo 'compiled tools ready'"]

FROM quality AS mutation-tools

RUN pip install --break-system-packages --ignore-installed --no-cache-dir mutmut==3.5.0

RUN . "$HOME/.cargo/env" && \
    cargo install cargo-mutants && \
    rm -rf /root/.cargo/registry /root/.cargo/git

CMD ["bash", "-lc", "mutmut --version && cargo mutants --version && echo 'mutation tools ready'"]
