# FR K8S 29 — Google Cloud mutation burst

## Summary

This add-on plans paid mutation-test shards on Google Cloud, but the default
implementation is no-spend. Mutation testing means changing code in small ways
to check whether tests catch the change. A dry run prints the plan, the spend
check result, and the command shape. A live paid run still needs an explicit
confirmation flag and a passing spend guard.

## Interface

- `scripts/gcp_burst_executor.py --dry-run` prints the Google Cloud Batch
  command and merge-compatible result record without spending money.
- A paid run requires `--project`, `--region`, `--budget-cap-eur`,
  `--max-vms`, `--billing-project`, `--billing-export-table`, and
  `--confirm-paid-run`.
- `scripts/gcp_spend_guard.py` reads the billing export table through the
  `bq` command-line tool and fails closed when spend cannot be checked.
- `scripts/distributed_test_coordinator.py --dry-run --burst gcp --full`
  plans Google Cloud mutation shards only when an injected spend result allows
  them. Without a spend result, it stays local-only.

## Safety Rules

- Missing project, region, budget cap, or VM count stops the run.
- Paid execution stops unless `--confirm-paid-run` is present.
- The default budget cap is 20 EUR, the refusal point is 18 EUR, and the
  default virtual machine count is 12. The exact defaults live in
  `scripts/gcp_burst_executor.py`.
- Google Cloud Budget notification files live in
  `infra/gcp/budget-autodisable/`, but the function is simulation-only until
  the operator turns live billing disable on in Google Cloud.
- The script does not delete local data, Docker volumes, or Kubernetes objects.
- Google warns that budget notifications can be delayed, so the budget
  notification is not treated as the only guard. The local spend guard and the
  per-run caps must pass before paid execution.

## Test Plan

- `python scripts/test_gcp_burst_executor.py`
- `python scripts/test_distributed_test_coordinator.py`
- `python scripts/gcp_burst_executor.py --project xf --region europe-west1 --dry-run`
- `python scripts/distributed_test_coordinator.py --dry-run --burst gcp --full`
- `python scripts/bazel_default.py test //tools/quality:all`

## Citations

- Google Cloud Batch pricing — no extra Batch service charge beyond the Google
  Cloud resources used by the jobs.
  https://cloud.google.com/batch/pricing
- Google Cloud Spot VMs — discounted virtual machines can be stopped or deleted
  at any time, so mutation shards must be retryable.
  https://cloud.google.com/compute/docs/instances/spot
- Google Cloud budget notifications — programmatic notifications can be sent to
  Pub/Sub and then to a function.
  https://cloud.google.com/billing/docs/how-to/notify
- Google Cloud disable billing with notifications — Google documents automatic
  billing disable, but warns that notification delay can allow extra spend.
  https://cloud.google.com/billing/docs/how-to/disable-billing-with-notifications
- Google Cloud billing export to BigQuery — detailed billing data can be
  exported and queried for cost checks.
  https://cloud.google.com/billing/docs/how-to/export-data-bigquery
