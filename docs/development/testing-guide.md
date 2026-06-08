# Development Testing Guide

This page used to describe a Lua test toolchain. Lua was removed from the project
on 2026-06-06 — the backend is now **Python + Rust only** (see
[ADR 0007](../adr/0007-python-rust-two-language.md)).

The single source of truth for how to run and write tests in this repo is
[`docs/TESTING.md`](../TESTING.md). It covers the Python (pytest), Rust
(`cargo test` / clippy / `cargo-mutants`), and frontend (Karma) layers, what
blocks a merge, and where new tests go.
