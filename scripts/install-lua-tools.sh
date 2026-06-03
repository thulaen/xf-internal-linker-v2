#!/usr/bin/env bash
set -euo pipefail

LUAJIT_VERSION="${LUAJIT_VERSION:-2.1.0-beta3}"
LUAROCKS_VERSION="${LUAROCKS_VERSION:-3.11.1}"
BUSTED_VERSION="${BUSTED_VERSION:-2.2.0-1}"
LUACHECK_VERSION="${LUACHECK_VERSION:-1.2.0-1}"
LUACOV_VERSION="${LUACOV_VERSION:-0.16.0-1}"
LUACOV_COBERTURA_VERSION="${LUACOV_COBERTURA_VERSION:-0.2-2}"
LUA_QUICKCHECK_VERSION="${LUA_QUICKCHECK_VERSION:-0.2-4}"

echo "Installing LuaJIT ${LUAJIT_VERSION} toolchain through LuaRocks ${LUAROCKS_VERSION}."
luarocks --lua-version=5.1 install busted "${BUSTED_VERSION}"
luarocks --lua-version=5.1 install luacheck "${LUACHECK_VERSION}"
luarocks --lua-version=5.1 install luacov "${LUACOV_VERSION}"
luarocks --lua-version=5.1 install luacov-cobertura "${LUACOV_COBERTURA_VERSION}"
luarocks --lua-version=5.1 install lua-quickcheck "${LUA_QUICKCHECK_VERSION}"
