# Mint GlitchTip Placement

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Sources

- [SPEC CITED: technical_doc] GlitchTip, "Installation," https://glitchtip.com/documentation/install
- [SPEC CITED: technical_doc] GlitchTip, "SDK Documentation," https://glitchtip.com/sdkdocs/
- [SPEC CITED: technical_doc] Docker, "Compose profiles," https://docs.docker.com/compose/how-tos/profiles/
- [SPEC CITED: technical_doc] PostgreSQL, "Client Authentication," https://www.postgresql.org/docs/current/client-authentication.html

## Scope

GlitchTip web and worker containers run on Mint. The GlitchTip database stays in the existing Windows Postgres container so the same login account continues to work. Redis also stays on Windows because Redis is part of the local control plane.

## BDD

Given Windows Postgres already contains the GlitchTip users table, When GlitchTip starts on Mint, Then it connects to `10.10.10.10:5432/glitchtip` and uses the same login rows.

Given Redis stays on Windows, When the Mint GlitchTip worker starts, Then it connects to `redis://10.10.10.10:6379/4`.

Given the dashboard must be opened from Windows, When GlitchTip runs on Mint, Then the web service listens on `http://10.10.10.91:1337`.

Given an operator supplies the existing GlitchTip email and password, When `scripts/check-mint-glitchtip.ps1` runs, Then the check authenticates that account through the Mint GlitchTip container against the Windows Postgres database.

[SPEC CITED: feature=fr-mint-glitchtip-placement kind=technical_doc id=https://glitchtip.com/documentation/install verified_at=2026-06-02]
