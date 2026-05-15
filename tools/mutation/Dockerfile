FROM golang:1.25-bookworm AS go-tools

RUN go install github.com/avito-tech/go-mutesting/cmd/go-mutesting@latest && \
    go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.12.2 && \
    go install github.com/securego/gosec/v2/cmd/gosec@latest

FROM ubuntu:24.04

ENV PATH="/usr/local/go/bin:${PATH}"
ARG INFER_VERSION=1.2.0

COPY --from=go-tools /usr/local/go /usr/local/go
COPY --from=go-tools /go/bin/go-mutesting /usr/local/bin/go-mutesting
COPY --from=go-tools /go/bin/golangci-lint /usr/local/bin/golangci-lint
COPY --from=go-tools /go/bin/gosec /usr/local/bin/gosec

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
      clang-format-19 \
      clang-tidy-19 \
      libclang-rt-19-dev \
      cppcheck \
      iwyu \
      lcov \
      xz-utils \
      python3 \
      python3-dev \
      python3-pip \
      python-is-python3 && \
    curl -1sLf 'https://dl.cloudsmith.io/public/mull-project/mull-stable/setup.deb.sh' | bash && \
    apt-get update && \
    apt-get install -y --no-install-recommends mull-19 && \
    curl -sSL "https://github.com/facebook/infer/releases/download/v${INFER_VERSION}/infer-linux-x86_64-v${INFER_VERSION}.tar.xz" \
      | tar -C /opt -xJ && \
    ln -s "/opt/infer-linux-x86_64-v${INFER_VERSION}/bin/infer" /usr/local/bin/infer && \
    pip install --break-system-packages --ignore-installed --no-cache-dir mutmut==3.5.0 pybind11==2.13.6 semgrep && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /repo

CMD ["bash", "-lc", "mutmut --version && mull-runner-19 --version && go version && command -v go-mutesting >/dev/null && golangci-lint --version && gosec -version && cmake --version && clang++-19 --version && clang-tidy-19 --version && cppcheck --version && include-what-you-use --version && infer --version && semgrep --version && echo 'compiled tools ready'"]
