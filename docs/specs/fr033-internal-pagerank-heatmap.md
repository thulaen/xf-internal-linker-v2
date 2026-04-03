# FR-033 - Internal PageRank (Structural Equity) Heatmap

## What's wanted
A heatmap to see which pages have the most "juice" (authority) and which have the least. This helps identify where internal links are too concentrated or too thin.

## Technical Requirements

### Backend Logic
- Reuse `march_2026_pagerank_score` (defined in FR-006).
- Use `SELECT MIN(pagerank), MAX(pagerank)` to compute the dynamic range for each run.
- Serve the data on the graph topology JSON.

### Frontend Rendering
- Use an Interpolate color scale (e.g., `d3.interpolateRdYlBu`) in the graph.
- Toggle switch: `Show Heatmap` in the graph settings.

## Specific Controls / Behaviour
- **Heat Colors**: High authority pages are bright red; low authority pages are deep blue.
- **Node Size**: Sizing nodes by PageRank makes authority disparities even more obvious.
- **Top Authorities Table**: List the top 20 "Power Pages" with their silo name and total in/out links.
- **Concentration Warning**: Display a clear alert if most of the link authority is concentrated on only a few pages (this is bad for site-wide SEO).

## Implementation Notes
- **Scaling**: Distances between node values can be huge. Use a `d3.scaleLog()` to ensure tiny PageRank scores are still visible and distinct.
- **Clarity**: Add a legend at the bottom of the graph to show what the colors mean (Red = High, Blue = Low).
- **Comparison**: Show a "Before vs. After" if the user has applied multiple suggestions, showing how the authority moved.
