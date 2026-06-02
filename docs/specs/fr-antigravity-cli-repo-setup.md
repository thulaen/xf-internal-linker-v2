# Antigravity CLI Repo Setup

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Sources

- Google Antigravity CLI getting started: https://www.antigravity.google/docs/cli-getting-started
- Local installed Antigravity CLI help, `agy --help`, observed 2026-05-26, version `1.0.2`.
- Local installed Antigravity plugin help, `agy plugin --help`, observed 2026-05-26.

## Scope

This setup covers the local Antigravity command-line tool for this repository. It does not store login files, model history, browser profiles, or any other personal Antigravity state in Git.

## Behavior

Given the operator starts Antigravity from this repository, When they use `scripts/start-antigravity.ps1`, Then the script runs `agy` from the repository root, adds this repository as an Antigravity workspace directory, and enables the Antigravity sandbox unless the operator explicitly disables it.

Given a caller tries to pass `--dangerously-skip-permissions`, When the launcher sees that argument, Then it stops before running Antigravity and explains that unsafe permission bypass is not allowed for this repository.

Given this repository already has Gemini local tool configuration, When `agy plugin import gemini` is run, Then Antigravity imports the Gemini tool configuration into the user's local Antigravity config area, not into tracked repo files.

## Verification

- `agy --version` prints `1.0.2`.
- `agy plugin import gemini` imports `chrome-devtools-mcp` from Gemini.
- `agy plugin list` lists `chrome-devtools-mcp` with `skills` and `mcpServers`.
- `python -m pytest -q scripts/test_antigravity_cli_setup.py` passes.

[SPEC CITED: feature=fr-antigravity-cli-repo-setup kind=technical_doc id=https://www.antigravity.google/docs/cli-getting-started verified_at=2026-06-02]
