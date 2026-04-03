# FR-031 - Interactive D3.js Force-Directed Link Graph

## What's wanted
The primary visualization for the Link Graph page: an interactive, zoomable, and pannable network graph of the site's internal links. This feature turns raw database edges into a visual map that operators can explore to understand site structure.

## Technical Requirements

### Backend API
- **Endpoint**: `GET /api/graph/topology/`
- **Response Format**:
  ```json
  {
    "nodes": [
      {
        "id": 101,
        "title": "Example Thread",
        "type": "thread",
        "silo_id": 5,
        "pagerank": 0.85,
        "in_degree": 12,
        "out_degree": 4
      }
    ],
    "links": [
      {
        "source": 101,
        "target": 202,
        "context": "contextual",
        "weight": 1.0
      }
    ]
  }
  ```

### Frontend Implementation (Angular + D3.js)
- **Library**: D3.js v7.
- **Component**: `GraphComponent` (existing placeholder).
- **Simulation**: Use `d3.forceSimulation()` with the following forces:
  - `forceLink`: Uses `link.weight` for strength.
  - `forceManyBody`: Strong negative charge to prevent crowding.
  - `forceCenter`: Keep the graph centered in the viewport.
  - `forceCollide`: Radius based on node PageRank to prevent overlap.

## Specific Controls / Behaviour
- **Visual Encoding**:
  - **Node Size**: Derived from `pagerank` (log scale).
  - **Node Color**: Mapping of `silo_id` to a categorical color scheme (e.g., D3 SchemeCategory10).
  - **Edge Thickness**: Constant for all links initially.
- **Interactivity**:
  - **Zoom & Pan**: Standard D3 zoom behavior on the SVG container.
  - **Node Dragging**: Users can drag nodes to manually layout clusters. Dragging fixes the node's position (pinned).
  - **Hover State**: Highlights neighbors and dim everything else. Tooltip displays `title`, `in_degree`, and `silo_id`.
  - **Focus Mode**: Clicking a node selects it and opens a sidebar with a list of all inbound/outbound links for that specific page.

## Implementation Notes
- **Large Graphs**: For sites with > 500 nodes, the force simulation can be heavy. Use `simulation.stop()` and then `simulation.tick(n)` during a loading state to pre-compute the layout before rendering.
- **SVG vs Canvas**: Start with SVG for ease of interactivity/event handling. Switch to Canvas only if performance degrades on typical forum datasets.
- **Responsive Design**: The SVG should resize dynamically to fill the `mat-card` container on the page.
