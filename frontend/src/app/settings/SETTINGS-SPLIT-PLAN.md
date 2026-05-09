# Settings Component Split — Plain-English Plan

## Why this matters

`settings.component.ts` is **4,683 lines**. CLAUDE.md's hard limit is 1,500 lines per file. The component owns nine tabs, every form, every save call, and every validation rule for the most-trafficked page in the app. It is the single most fragile file in the frontend.

## What's already extracted

The team has been chipping away at this for a while:

| Tab | Status | Component file |
|---|---|---|
| 1. Ranking Weights | **In settings.component.html** (lines 64-1519, 14 sub-cards) | — |
| 2. Silo Architecture | In settings.component.html (lines 1520-1658) | — |
| 3. Connect & Sync | In settings.component.html (lines 1659-2455) | — |
| 4. Library & History | In settings.component.html (lines 2456-2835) | — |
| 5. Notifications | Mixed | — |
| 6. Diagnostics | Partial | `WeightDiagnosticsCardComponent`, `PassageRelevanceCardComponent` |
| 7. Performance | **Extracted** | `PerformanceSettingsComponent` |
| 8. Helpers | **Extracted** | `HelpersSettingsComponent` |
| 9. Meta Algorithms | **Extracted** | `MetaAlgorithmsTabComponent` |

This session also extracted the page-top stat strip → `SettingsOverviewComponent`.

## What still needs to move

### Tab 1 — Ranking Weights (BIGGEST WIN)

The Ranking Weights tab has 14 sub-cards (PageRank, Link Freshness, Phrase Matching, Learned Anchors, Rare Term, Field-Aware Relevance, Traffic & Search Signals, Click Distance, Spam Guards, Feedback Reranking, Near-Duplicate Clustering, Slate Diversity, Graph Candidates, Value-Model Scoring). Each sub-card is a self-contained unit of state + UI.

**Plan:** make `RankingWeightsTabComponent` and one sub-component per card. The sub-cards talk to a shared `RankingWeightsService` that owns the form state and the save call. The parent tab keeps a thin co-ordination role only.

Estimated effort: **6-8 hours** of careful extraction with testing after each card. There is no shortcut — every shared property in the parent file has 3-5 consumers across these sub-cards, and getting the dependency direction wrong breaks the page.

### Tab 2 — Silo Architecture

Self-contained tab, ~140 lines of HTML plus a `SiloSettingsService` that already exists. Pull the HTML into `SiloArchitectureTabComponent` and rebind `siloGroups`, `scopes`, `assignedScopeCount`. ~2 hours.

### Tab 3 — Connect & Sync

XenForo + WordPress + GSC + GA4 + Matomo connection cards. ~800 lines of HTML, four separate services already exist. Each connection becomes one sub-component. ~6 hours.

### Tab 4 — Library & History

Weight-preset library and adjustment history. Already has `WeightAdjustmentHistory` and `WeightPreset` interfaces but the UI is inline. Extract to `LibraryHistoryTabComponent`. ~3 hours.

### Tab 5 — Notifications

Notification preferences (email, desktop, audio cues). Three services already exist. Extract to `NotificationsTabComponent`. ~2 hours.

### After all extractions

The parent `SettingsComponent` should be:
- Tab navigation glue (selectedTabIndex, tabFragmentMap, the `mat-tab-group` template)
- Page header with the "Save all" button
- A coordination layer that asks each child tab "are you dirty?" / "save yourself"

Target size after split: **under 500 lines** for the parent component.

## Why this isn't done in one session

Each extraction has its own regression surface. A hidden two-way binding between Tab 1 and Tab 6 can break "Save all". The only safe way is:

1. Run the full test suite (`npm run test:ci`) before each extraction.
2. Extract one tab.
3. Run tests + a Playwright smoke test (`ui:test:live`) against the actual settings page.
4. Manually exercise Save All on the live stack.
5. Repeat.

That's why each tab gets its own commit and its own session.

## How to track progress

- One issue per tab (file in the auto-issues registry as `agent`-source AutoIssue rows).
- Burn-down: parent file should drop by 500-1500 lines per session as tabs come out.
- Done definition: `wc -l settings.component.ts` ≤ 500.
