# Go contract-testing placeholder

This directory exists so future Go services can grow Pact provider-verification tests in a consistent location. As of 2026-05-12, no contracts live here.

When the first Go HTTP service lands:

1. Install the Pact Go SDK: `go get github.com/pact-foundation/pact-go/v2/...`
2. Add a provider-verification test file alongside the service: `services/go/<service>/pact_provider_test.go`
3. Wire a CI job that runs the verification against the consumer-side Pact JSON files the Angular frontend publishes to `frontend/pacts/`

See [`docs/CONTRACT-TESTING.md`](../../../docs/CONTRACT-TESTING.md) for the project-wide contract-testing standard and the existing Angular ↔ Django scaffold.
