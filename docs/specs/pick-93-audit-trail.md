# Pick 93 - Unified Audit Trail

## Citation

Martin Fowler, 2005, "Event Sourcing", canonical article at martinfowler.com.

## Required Behavior

Every operator action that changes application state writes one row to `AuditEvent` through the single `record_audit(...)` helper.

Covered actions include settings changes, ranking weight tuning, master pause toggles, runtime model promote or drain actions, and suggestion approve or reject batches.

The audit trail is controlled by `system.audit_log_enabled`, which defaults to true in the Recommended preset.
