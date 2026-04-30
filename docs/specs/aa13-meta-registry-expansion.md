# AA.13 - Meta Registry Expansion

## Requirement

The Meta Algorithms Settings tab lists every registry entry: active implemented meta-algorithms plus forward-declared specs.

Forward-declared entries are visible by default, cannot be enabled, and use the `disabled-pending-implementation` state. The UI shows them as spec-only rows and opens this spec through the shared `SpecViewerDialog`.

## Acceptance

The tab shows all 249 rows by default. Implemented rows can still be toggled. Spec-only rows are visually distinct and remain disabled until implementation code is added.
