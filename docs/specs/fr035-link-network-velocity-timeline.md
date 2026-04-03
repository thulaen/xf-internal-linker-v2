# FR-035 - Link Freshness & Churn Velocity Timeline

## What's wanted
A history of how the link network is changing. This monitors "Link Churn" (how often links appear and disappear) and new link discovery over time.

## Technical Requirements

### Backend API Attributes
- Expand `GET /api/graph/topology/` to include a daily `metrics` summary:
  ```json
  {
    "nodes": [...],
    "links": [...],
    "history": [
      { "date": "2026-03-01", "created": 15, "deleted": 2 },
      { "date": "2026-03-02", "created": 8, "deleted": 1 }
    ]
  }
  ```

### Frontend View
- Add a new "Freshness" tab with a Chart.js stacked area chart.
- Show "Links Created" vs. "Links Disappeared" over time.

## Specific Controls / Behaviour
- **Velocity Chart**: Grouping by `tracked_at` date or `last_seen_at` to compute daily deltas.
- **Churn Alert**: Highlight nodes in the graph that have high link turnover (links that appear and disappear repeatedly).
- **Time Filter**: Use a slider to "scrub" through the graph history to see how it looked 30 days ago vs. today.

## Implementation Notes
- **Scaling**: For very large sites (>1 million links), querying `LinkFreshnessEdge` history should use pre-aggregated daily summaries.
- **Data Source**: Use the existing `LinkFreshnessEdge` table which already tracks `first_seen_at` and `last_seen_at`.
- **Action**: Selecting a node in the graph shows its "first linked" date and "most recently seen" date.
