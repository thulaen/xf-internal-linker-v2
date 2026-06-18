# Google Cloud budget auto-disable rehearsal

This folder holds the no-spend setup files for slice 29. They are not applied
by default. The function stays in simulation mode unless the operator later
sets `SIMULATE_DEACTIVATION=false` inside Google Cloud.

## What It Protects

Given a Google Cloud budget sends a notification, when the function receives
that notification, then simulation mode records what would happen and does not
disable billing.

Given a later operator deliberately turns simulation off, when the budget
threshold is reached, then the function can remove billing from the configured
project. Google documents this pattern, but also warns that budget notification
delays can allow extra spend, so the local spend guard remains required.

## Files

- `main.tf` declares the budget notification topic, budget, and function shape.
- `batch-job-template.json` is the Batch job template path used by the dry-run
  command.
- `function/main.py` keeps the billing-disable decision in one small tested
  function.
- `function/requirements.txt` names only the Google packages needed by a live
  Cloud Run function deployment.
