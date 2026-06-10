# Turbo Mutation Images

## Overview
As of June 2026, heavy mutation testing binaries (`cargo-mutants`, `mull-19`, `mutmut`) have been extracted from the base `backend-quality` and `compiled-tools` Docker images.

## Structure
They are now housed in dedicated targets:
- `backend-mutation-tools`
- `compiled-mutation-tools`

## Purpose
This prevents the MSI Windows host from pulling gigabytes of unused mutation binaries during local developer checks, while allowing the Dell helper to cleanly route turbo mutations to the isolated images.
