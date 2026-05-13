FROM golang:1.25-bookworm AS go-tools

RUN go install github.com/avito-tech/go-mutesting/cmd/go-mutesting@latest

FROM ubuntu:24.04

ENV PATH="/usr/local/go/bin:${PATH}"

COPY --from=go-tools /usr/local/go /usr/local/go
COPY --from=go-tools /go/bin/go-mutesting /usr/local/bin/go-mutesting

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      cmake \
      build-essential \
      libtbb-dev \
      clang-19 \
      python3 \
      python3-pip \
      python-is-python3 && \
    curl -1sLf 'https://dl.cloudsmith.io/public/mull-project/mull-stable/setup.deb.sh' | bash && \
    apt-get update && \
    apt-get install -y --no-install-recommends mull-19 && \
    pip install --break-system-packages --no-cache-dir mutmut==3.5.0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /repo

CMD ["bash", "-lc", "mutmut --version && mull-runner-19 --version && go version && command -v go-mutesting >/dev/null && echo 'mutation tools ready'"]
