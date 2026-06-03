FROM rust:1.83-bookworm AS lua-tools-build

COPY services/speccheck /tmp/speccheck
RUN cargo install --path /tmp/speccheck/crates/lua_fastcheck --locked --root /opt/lua-tools && \
    cargo install --path /tmp/speccheck/crates/lua_mutmut --locked --root /opt/lua-tools

FROM ubuntu:24.04

ARG BUSTED_VERSION=2.2.0-1
ARG LUACHECK_VERSION=1.2.0-1
ARG LUACOV_VERSION=0.16.0-1
ARG LUACOV_COBERTURA_VERSION=0.2-1
ARG LUA_QUICKCHECK_VERSION=0.2-4

COPY --from=lua-tools-build /opt/lua-tools/bin/lua-fastcheck /usr/local/bin/lua-fastcheck
COPY --from=lua-tools-build /opt/lua-tools/bin/lua-mutmut /usr/local/bin/lua-mutmut

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      build-essential \
      git \
      luajit \
      luarocks && \
    luarocks --lua-version=5.1 install busted "${BUSTED_VERSION}" && \
    luarocks --lua-version=5.1 install luacheck "${LUACHECK_VERSION}" && \
    luarocks --lua-version=5.1 install luacov "${LUACOV_VERSION}" && \
    luarocks --lua-version=5.1 install luacov-cobertura "${LUACOV_COBERTURA_VERSION}" && \
    luarocks --lua-version=5.1 install lua-quickcheck "${LUA_QUICKCHECK_VERSION}" && \
    ln -s /usr/local/bin/lua-mutmut /usr/local/bin/luamut && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /repo

CMD ["bash", "-lc", "command -v lua-fastcheck >/dev/null && lua-mutmut --version && luamut --version && luajit -v && busted --version && luacheck --version && luacov --version && echo 'lua quality tools ready'"]
