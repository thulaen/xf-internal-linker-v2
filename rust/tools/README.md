# xftool

The single Rust command-line multi-tool for this repo: one binary, many grouped
subcommands (`xftool <group> <verb-noun>`). See
[ADR 0008](../../docs/adr/0008-tooling-languages-rust-cli-python.md) and
[fr-rust-cli-tooling](../../docs/specs/fr-rust-cli-tooling.md).

This is **tooling, not app architecture**: the Django app and the kernel crates
never depend on it. It is for CI checks, log forensics, data cleanup, and
auditing only.

## Conventions (every subcommand obeys)

- **Read-only by default.** A tool that mutates state requires an explicit
  `--apply` (dry-run is the default).
- **Machine-readable output.** `--format json|table|csv` (default `table`).
- **CI exit codes.** `0` ok, `1` findings/violations, `2` usage/internal error.
- **Cross-platform.** No PowerShell, no host assumptions.

## Discover the catalog

```
xftool list                 # all subcommands, grouped
xftool list --format json   # machine-readable catalog
```

## Build & test (Dell only)

```
/usr/bin/bash scripts/dell-rust.sh fmt --check
/usr/bin/bash scripts/dell-rust.sh clippy -p xftool --all-targets -- -D warnings
/usr/bin/bash scripts/dell-rust.sh test -p xftool
```
