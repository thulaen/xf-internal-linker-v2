# FR-037 - Silo Connectivity & Cross-Topic Leakage Map

## What's wanted
A visualization for the integrity of content "Silos". This helps find where authority is "leaking" between different topical silos or where silos are isolated.

## Technical Requirements

### Backend API Attributes
- Expand `GET /api/graph/topology/` to include a `silo_id` or `silo_name` per node.
- Identify all "Cross-Silo" edges: `ExistingLink WHERE from.silo_id != to.silo_id`.

### Frontend View
- Add a new "Silo Boundaries" toggle in the graph settings.
- Use a Force-Directed layout variation that clusters by `silo_id`.

## Specific Controls / Behaviour
- **Leakage Audit**: Highlight all edges that go from one silo to a different silo.
- **Silo Integrity Score**: Compute a "Silo Score" for each silo (High = mostly internal links; Low = lots of cross-silo "leakage").
- **Isolated Silo Warning**: Display a clear alert if a silo has plenty of internally-pointing links but no connections back to the site-wide authority.

## Implementation Notes
- **Scaling**: For very large sites (>100 silos), only show top 10 most "leaky" silos by default.
- **Data Source**: Use existing `ContentItem.silo_group` association (FR-005).
- **Action**: Hovering a silo boundary in the graph highlights the whole silo and its connections.
- **Action**: Selecting a silo in the audit list centers it in the graph view.
