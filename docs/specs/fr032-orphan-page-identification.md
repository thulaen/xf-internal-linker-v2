# FR-032 - Automated Orphan & Low-Authority Page Identification

## What's wanted
SEO audit for "lost" or "dark" content. This feature finds pages that are disconnected from the site structure (orphans) or buried so deep that they have no importance.

## Technical Requirements

### Backend Logic
- **Orphan Query**: `SELECT * FROM ContentItem WHERE inbound_link_count = 0;` (already stored).
- **Low Integrity Flag**: Calculate the 5th percentile of PageRank scores and flag nodes below it.
- **Click Depth (Optional/Phase 2)**: Breadth-first search from a defined "root" page to find nodes with distance > 5.

### Frontend View
- **Tab Layout**: Add a new "Audits" tab next to the graph.
- **DataTable**: `mat-table` with `title`, `url`, `silo`, `inbound_link_count`, and `pagerank`.
- **Filtering**: Dropdown to show "All Orphan Pages" or "Low-Authority Hubs".

## Specific Controls / Behaviour
- **Visual Alert**: In the D3 graph, orphan nodes are colored with a high-contrast danger color (e.g., bright orange).
- **One-Click Suggestion**: Add a "Suggest Links" button for each entry. Clicking it triggers an immediate pipeline run focused only on finding inbound suggestions for that specific page.
- **Export**: Export the orphan list as a CSV file for manual work in external tools.

## Implementation Notes
- **Scalability**: For very large sites (>100k pages), the orphan list might be thousands of rows. Use standard server-side pagination for the DataTable.
- **Terminology**: Ensure the UI uses plain English terms like "Pages with no links" instead of "Orphans" for better accessibility.
- **Action Link**: Clicking the page title in the audit table should focus it in the D3 graph visualization.
