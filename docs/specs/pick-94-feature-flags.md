# Pick 94 - Feature Flags With Sticky Bucketing

## Citation

Tang et al., 2010, "Overlapping Experiment Infrastructure: More, Better, Faster Experimentation", Google.

## Required Behavior

Feature flags are declared in `apps/core/feature_flags.py`. New declared flags ship on by default unless a rollout percentage or operator override says otherwise.

For percentage rollouts, bucket assignment must be sticky: the same flag key and user id always produce the same decision.

Every evaluated flag can record an exposure event so operators can see which users encountered a gated behavior.
