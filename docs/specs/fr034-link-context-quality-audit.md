# FR-034 - Link Context & Contextual Class Audit

## What's wanted
A high-quality link audit focusing on "human-like" contextual placements. This helps distinguish between links buried in a footer and links dropped naturally inside an article's body.

## Technical Requirements

### Backend API Attributes
- Expand `GET /api/graph/topology/` to include `context` strings for each link edge: `contextual`, `weak_context`, or `isolated`.
- Already extracted and classified in `GraphSyncService.cs`.

### Frontend View
- Add a new "Qualities" tab to the graph view.
- Chart.js pie chart: % of site links by Context Class.
- Chart.js bar chart: # of links by `anchor_text` frequency per page.

## Specific Controls / Behaviour
- **Context Filters**: Filter the D3 graph to only show "contextual" links to see the "true" body-content network.
- **Anchor Warning**: Flag links with "over-optimized" anchors (e.g., thousands of links with the exact same keyword text and no variations).
- **Link Quality Score**: Simple per-page score representing the average quality of inbound links (High = mostly contextual; Low = mostly isolated).

## Implementation Notes
- **Clustering**: Group nodes in the graph by `contextual` density. Pages with many contextual links should naturally cluster together.
- **Tooltip detail**: The mouseover tooltip should show the most common anchor text used for that specific inbound link to the target page.
- **Action**: Hovering a specific "isolated" link in the audit list should blink the edge in the graph to show where that weak link is hidden.
