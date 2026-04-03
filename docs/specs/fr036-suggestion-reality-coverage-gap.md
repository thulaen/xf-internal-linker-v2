# FR-036 - Suggestion vs. Reality Coverage Gap Analysis

## What's wanted
A high-relevancy link audit comparing the current structural state (the Link Graph) to the potential structural state (the AI Ranker Suggestions). This identifies "Opportunity Gaps" where high-relevance links could exist but don't.

## Technical Requirements

### Backend Logic
- New `GET /api/graph/gap-analysis/` endpoint.
- Compare existing nodes with `Suggestion` rows. Find all suggestions where `status == 'pending'` and `score_final > 0.8` (or user-defined threshold).
- Return these as "Ghost Edges" in the graph topology.

### Frontend View
- Add a new "Gaps" toggle to the graph settings.
- Show "Ghost Edges" as dotted lines between nodes.

## Specific Controls / Behaviour
- **Gap Score**: Compute a "Neglect Score" for each node (High AI Relevance Sum + Low Actual Inbound Count).
- **Interactive Action**: Clicking a ghost edge opens a compact "Quick Approve" popover with the suggestion details and anchor text.
- **Filtering**: Slider to filter ghost edges by `score_final` (e.g., only show top 5% of gaps).

## Implementation Notes
- **Scaling**: For very large sites (>100k nodes), only calculate gap analysis on nodes that are currently visible or selected to save on processing.
- **Data Source**: Join `ContentItem` with `Suggestion` on `target_content_id`.
- **Clarity**: Ensure the difference between "Existing Link" and "Potential Link" is obvious in the graph.
- **Action**: Hovering a ghost edge shows why the link was suggested in a small popup (e.g., "Very high keyword relevance").
