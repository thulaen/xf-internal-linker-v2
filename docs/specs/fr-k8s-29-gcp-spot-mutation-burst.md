# FR K8S 29 — Google Cloud mutation burst

## Summary

This add-on runs paid mutation-test shards on Google Cloud only when the operator
explicitly confirms the run. Mutation testing means changing code in small ways
to check whether tests catch the change.

## Interface

- `scripts/gcp_burst_executor.py --dry-run` prints the containerized Google
  Cloud command without spending money.
- A paid run requires `--project`, `--region`, `--budget-cap-eur`,
  `--max-vms`, and `--confirm-paid-run`.
- The command uses the official Google Cloud SDK container because `gcloud` is
  not installed on MSI.

## Safety Rules

- Missing project, region, budget cap, or VM count stops the run.
- Paid execution stops unless `--confirm-paid-run` is present.
- The default budget cap is 20 EUR and the default VM count is 12.
- The script does not delete local data, Docker volumes, or Kubernetes objects.

## Test Plan

- `python scripts/test_gcp_burst_executor.py`
- `python scripts/gcp_burst_executor.py --project xf --region europe-west1 --dry-run`

## Citations

- Google Cloud Batch documentation — "Create and run a basic job".
  https://cloud.google.com/batch/docs/create-run-basic-job
- Google Cloud SDK Docker image documentation.
  https://cloud.google.com/sdk/docs/downloads-docker
- Google Cloud budgets documentation — "Create, edit, or delete budgets and alerts".
  https://cloud.google.com/billing/docs/how-to/budgets
