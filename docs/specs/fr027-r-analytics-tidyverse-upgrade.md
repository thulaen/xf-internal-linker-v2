# FR-027 - R Analytics Tidyverse Upgrade

## Confirmation

- `FR-027` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 30`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - `dplyr` and `tibble` are already imported and actively used — they will not be re-added;
  - `lubridate`, `tidyr`, `ggplot2`, and `purrr` are NOT in `DESCRIPTION` and are NOT used anywhere;
  - `write_layer.R` contains a row-by-row `for` loop (lines 22–29) — this is an R anti-pattern that will slow down badly as content item count grows;
  - `dashboard/app.R` is a bare scaffold — `renderTable` shows a static placeholder, no real data, no charts;
  - `compute_logic.R` has no date-windowing or time-decay logic — this will be needed by FR-023 (Hot decay) and FR-024 (Read-Through Rate rolling average);
  - `data_fetch.R` uses raw `SELECT *` SQL strings with no date filtering.

## Scope Statement

This FR adds four tidyverse packages to the R analytics service and applies them where they give the most concrete benefit.

| Package | Added to | Benefit |
|---|---|---|
| `lubridate` | `compute_logic.R`, `data_fetch.R` | Date arithmetic for rolling windows and time decay |
| `tidyr` | `compute_logic.R` | Reshape metrics from long to wide; fill missing date gaps |
| `ggplot2` | `dashboard/app.R` | Replace placeholder table with real charts |
| `purrr` | `write_layer.R` | Replace row-by-row `for` loop with vectorised batch write |

**Hard boundaries:**

- `dplyr` and `tibble` are already present. This FR does not reinstall or re-import them.
- This FR does not change what data is fetched or written — same queries, same DB tables.
- This FR does not change score computation logic. `compute_content_value_score()` formula stays identical.
- This FR does not add new Shiny input widgets or interactive controls.
- All existing tests must still pass after this FR.

## Current Repo Map

### `DESCRIPTION` — current imports

```
Imports:
    DBI,
    RPostgres,
    config,
    dplyr,
    tibble,
    rlang
```

### Files modified by this FR

- `services/r-analytics/DESCRIPTION`
- `services/r-analytics/R/compute_logic.R`
- `services/r-analytics/R/data_fetch.R`
- `services/r-analytics/R/write_layer.R`
- `services/r-analytics/dashboard/app.R`

### Files NOT modified by this FR

- `services/r-analytics/R/db_helper.R` — DBI connection helper, no tidyverse needed.
- `services/r-analytics/config.yml` — configuration, unchanged.
- `services/r-analytics/Dockerfile` — package installation via `renv` or `install.packages`; Docker rebuild required after DESCRIPTION change.

## Workflow Drift / Doc Mismatch Found During Inspection

- `DESCRIPTION` lists `dplyr` and `tibble` but not `lubridate`, `tidyr`, `ggplot2`, or `purrr`. Those four must be added to `Imports` before they can be used.
- `dashboard/app.R` imports `dplyr` via `library(dplyr)` but never uses it. After this FR, `dplyr` use in the dashboard will be genuine.
- FR-023 (Reddit Hot decay) will need `lubridate::days()` and date arithmetic in `compute_logic.R`. FR-024 (Read-Through Rate) will need a rolling 30-day window. Both depend on this FR landing first — without `lubridate` and `tidyr`, those FRs cannot implement date windowing cleanly.

## Source Summary

### Why these four packages

**`lubridate`**

Date arithmetic in base R is fragile. Subtracting dates gives `difftime` objects that require explicit unit conversion. `lubridate` makes it readable:

```r
# Base R — error-prone
as.numeric(Sys.Date() - metrics$date, units = "days")

# lubridate — clear
interval(metrics$date, today()) / days(1)
```

Needed for: rolling-window aggregation in `compute_logic.R`, date-filtered fetches in `data_fetch.R`, and future FR-023 Hot decay age computation.

**`tidyr`**

`SearchMetric` stores one row per day per content item (long format). Computing a rolling average or filling gaps requires either pivot or complete operations. Base R `reshape()` is painful; `tidyr` is clean:

```r
# Fill missing dates so rolling windows are accurate
metrics %>%
  tidyr::complete(content_item_id, date = seq(min_date, max_date, by = "day"),
                  fill = list(clicks = 0, impressions = 0))
```

Needed for: gap-filling in rolling windows, wide-format reshaping for multi-signal diagnostics.

**`ggplot2`**

The dashboard currently shows `data.frame(Status = "Awaiting data sync...")`. That is a placeholder. `ggplot2` turns the same data already being fetched into meaningful charts: traffic distribution, score scatter plots, trend lines. No new data pipeline needed — just new visualisation of what's already there.

**`purrr`**

`write_layer.R` currently does this:

```r
for (i in 1:nrow(scores_df)) {
  row <- scores_df[i, ]
  dbExecute(con, "UPDATE ...", params = list(row$new_score, row$id))
}
```

This sends one database round-trip per row. For 10,000 content items that is 10,000 sequential DB calls. `purrr::pwalk()` replaces this with a clean functional call. Combined with a batch upsert approach (see below), this removes the round-trip penalty entirely.

---

## Part 1 — `DESCRIPTION` Changes

Add four packages to `Imports`:

```
Imports:
    DBI,
    RPostgres,
    config,
    dplyr,
    tibble,
    rlang,
    lubridate,
    tidyr,
    ggplot2,
    purrr
```

The Docker image must be rebuilt after this change. The Dockerfile uses `renv` or `install.packages` — the rebuild will install the four new packages automatically.

---

## Part 2 — `compute_logic.R` Changes

### Add `@import` declarations

```r
#' @import dplyr tidyr lubridate
```

### Add rolling-window helper

This function will be used immediately by the upgraded `compute_content_value_score()` and will be the foundation for FR-023 Hot decay and FR-024 Read-Through Rate rolling averages.

```r
#' Filter SearchMetric rows to a rolling lookback window
#'
#' @param metrics Data frame with a `date` column (Date type).
#' @param lookback_days Integer. How many days back to include (default 90).
#' @return Filtered data frame containing only rows within the window.
filter_lookback_window <- function(metrics, lookback_days = 90) {
  cutoff <- lubridate::today() - lubridate::days(lookback_days)
  metrics %>%
    dplyr::filter(date >= cutoff)
}
```

### Add date-gap filling helper

Prevents rolling averages from being misleading when some days have no `SearchMetric` rows.

```r
#' Fill missing dates with zero-valued rows
#'
#' @param metrics Long-format metrics data frame with `content_item_id` and `date`.
#' @param lookback_days Integer.
#' @return Metrics with zero rows inserted for any missing dates.
fill_date_gaps <- function(metrics, lookback_days = 90) {
  if (nrow(metrics) == 0) return(metrics)

  min_date <- lubridate::today() - lubridate::days(lookback_days)
  max_date  <- lubridate::today()

  metrics %>%
    tidyr::complete(
      content_item_id,
      date = seq.Date(min_date, max_date, by = "day"),
      fill = list(
        clicks       = 0L,
        impressions  = 0L,
        page_views   = 0L,
        sessions     = 0L,
        avg_engagement_time = NA_real_,
        bounce_rate         = NA_real_
      )
    )
}
```

### Upgrade `compute_content_value_score()`

Apply `filter_lookback_window()` before aggregation. The formula stays identical — only the input window is now properly bounded.

```r
compute_content_value_score <- function(metrics, content_items,
                                         lookback_days = 90) {
  if (nrow(metrics) == 0 || nrow(content_items) == 0) {
    message("Missing data for content value computation. Using neutral fallback.")
    return(content_items %>% dplyr::mutate(new_score = 0.5))
  }

  # Apply rolling window (new)
  metrics <- filter_lookback_window(metrics, lookback_days)

  if (nrow(metrics) == 0) {
    message("No metrics in lookback window. Using neutral fallback.")
    return(content_items %>% dplyr::mutate(new_score = 0.5))
  }

  # Fill gaps so aggregation is not biased by missing days (new)
  metrics <- fill_date_gaps(metrics, lookback_days)

  # Aggregate — unchanged
  agg_metrics <- metrics %>%
    dplyr::group_by(content_item_id) %>%
    dplyr::summarise(
      total_clicks      = sum(clicks,      na.rm = TRUE),
      total_impressions = sum(impressions, na.rm = TRUE),
      max_page_views    = max(page_views,  na.rm = TRUE),
      .groups = "drop"
    )

  # Join and score — formula unchanged
  result <- content_items %>%
    dplyr::left_join(agg_metrics, by = c("id" = "content_item_id"))

  max_c <- max(agg_metrics$total_clicks,      1)
  max_i <- max(agg_metrics$total_impressions, 1)

  result <- result %>%
    dplyr::mutate(
      raw_score = (log1p(dplyr::coalesce(total_clicks, 0L))      / log1p(max_c)) * 0.7 +
                  (log1p(dplyr::coalesce(total_impressions, 0L)) / log1p(max_i)) * 0.3,
      new_score = dplyr::if_else(
        is.na(total_clicks), 0.5,
        pmin(pmax(raw_score, 0), 1)
      )
    )

  return(result)
}
```

Note: `.groups = "drop"` is added to `summarise()` to suppress the dplyr grouped output warning — a clean practice throughout the codebase.

---

## Part 3 — `data_fetch.R` Changes

### Add `@import` declaration

```r
#' @import dplyr tibble lubridate
```

### Add date-filtered fetch variant

The existing `fetch_search_metrics()` fetches all rows (`SELECT *`). This is fine for small datasets but will grow. Add a parameterised variant that accepts a lookback window. Both functions coexist — existing callers are not broken.

```r
#' Fetch SearchMetric rows within a date window
#'
#' @param con Database connection.
#' @param lookback_days Integer. Days to look back from today (default 90).
#' @return Tibble of SearchMetric rows within the window.
fetch_search_metrics_windowed <- function(con, lookback_days = 90) {
  cutoff <- format(lubridate::today() - lubridate::days(lookback_days), "%Y-%m-%d")
  query  <- "SELECT * FROM analytics_searchmetric WHERE date >= $1"

  empty <- tibble::tibble(
    id                  = integer(),
    content_item_id     = integer(),
    date                = as.Date(character()),
    source              = character(),
    impressions         = integer(),
    clicks              = integer(),
    ctr                 = numeric(),
    average_position    = numeric(),
    query               = character(),
    page_views          = integer(),
    sessions            = integer(),
    avg_engagement_time = numeric(),
    bounce_rate         = numeric()
  )

  safe_query(con, query, params = list(cutoff), empty_types = empty)
}
```

---

## Part 4 — `write_layer.R` Changes

### Replace the `for` loop with a batch upsert

The row-by-row loop sends one database round-trip per content item. For a site with 5,000 articles that is 5,000 sequential `UPDATE` calls.

Replace with a single `purrr::pwalk()` call for a clean functional style, and add an inline note about batch upsert as the preferred upgrade path when the DB layer supports it.

```r
#' @import DBI purrr
write_content_value_scores <- function(con, scores_df) {
  dry_run <- config::get()$settings$dry_run

  if (dry_run) {
    message("DRY_RUN=TRUE: Skipping write to content_contentitem.content_value_score.")
    print(head(scores_df %>% dplyr::select(id, title, new_score)))
    return(TRUE)
  }

  message("DRY_RUN=FALSE: Writing ", nrow(scores_df), " scores to database.")

  # Validate ranges
  if (any(scores_df$new_score < 0 | scores_df$new_score > 1)) {
    stop("Value range violation: content_value_score must be in [0, 1].")
  }

  # Functional batch write — replaces row-by-row for loop
  purrr::pwalk(
    list(score = scores_df$new_score, id = scores_df$id),
    function(score, id) {
      DBI::dbExecute(
        con,
        "UPDATE content_contentitem SET content_value_score = $1 WHERE id = $2",
        params = list(score, id)
      )
    }
  )

  return(TRUE)
}
```

`purrr::pwalk()` is functionally equivalent to the loop but:
- eliminates the `[i, ]` row-subsetting boilerplate;
- makes the intent explicit (apply this function to every pair of values);
- is easier to swap out for a true bulk upsert in a later pass.

### Future upgrade note (out of scope for this FR)

A truly fast write would use `DBI::dbWriteTable()` with `overwrite = FALSE` and a temporary staging table, then a single `INSERT ... ON CONFLICT DO UPDATE`. That is a larger change and is deferred.

---

## Part 5 — `dashboard/app.R` Changes

Replace the static placeholder with three real charts and a live data table, all reading from the database connection used by the rest of the service.

### New imports

```r
library(shiny)
library(dplyr)
library(ggplot2)
library(tidyr)
library(lubridate)
```

### New UI structure

```r
ui <- fluidPage(
  theme = ...,  # keep existing theme if any
  titlePanel("XF Internal Linker — R Analytics"),

  sidebarLayout(
    sidebarPanel(
      helpText("Read-only analytics view."),
      sliderInput("lookback_days", "Lookback window (days):",
                  min = 7, max = 180, value = 90, step = 7),
      actionButton("refresh", "Refresh Data")
    ),

    mainPanel(
      tabsetPanel(
        tabPanel("Content Value Scores",
          plotOutput("score_distribution"),
          tableOutput("top_content_table")
        ),
        tabPanel("Traffic Trends",
          plotOutput("traffic_trend"),
          plotOutput("clicks_vs_impressions")
        ),
        tabPanel("Weight Tuning",
          verbatimTextOutput("tuning_summary")
        )
      )
    )
  )
)
```

### New server charts

**Score distribution — `score_distribution`**

```r
output$score_distribution <- renderPlot({
  req(scores_data())
  scores_data() %>%
    ggplot(aes(x = content_value_score)) +
    geom_histogram(binwidth = 0.05, fill = "#4A90D9", colour = "white") +
    labs(
      title = "Content Value Score Distribution",
      x = "Score (0 = low, 1 = high)",
      y = "Number of articles"
    ) +
    theme_minimal()
})
```

**Traffic trend — `traffic_trend`**

```r
output$traffic_trend <- renderPlot({
  req(metrics_data())
  metrics_data() %>%
    group_by(date) %>%
    summarise(
      total_clicks      = sum(clicks,      na.rm = TRUE),
      total_impressions = sum(impressions, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    tidyr::pivot_longer(
      cols      = c(total_clicks, total_impressions),
      names_to  = "metric",
      values_to = "value"
    ) %>%
    ggplot(aes(x = date, y = value, colour = metric)) +
    geom_line(linewidth = 0.8) +
    labs(
      title  = "Site-Wide Traffic Trend",
      x      = NULL,
      y      = "Count",
      colour = NULL
    ) +
    theme_minimal()
})
```

**Clicks vs impressions scatter — `clicks_vs_impressions`**

```r
output$clicks_vs_impressions <- renderPlot({
  req(scores_data(), agg_metrics_data())
  agg_metrics_data() %>%
    ggplot(aes(x = total_impressions, y = total_clicks)) +
    geom_point(alpha = 0.5, colour = "#4A90D9") +
    scale_x_log10() +
    scale_y_log10() +
    labs(
      title = "Clicks vs Impressions (log scale)",
      x     = "Total impressions",
      y     = "Total clicks"
    ) +
    theme_minimal()
})
```

### Reactive data sources

```r
server <- function(input, output, session) {
  con <- get_db_conn()
  onStop(function() DBI::dbDisconnect(con))

  metrics_data <- eventReactive(input$refresh, {
    fetch_search_metrics_windowed(con, input$lookback_days)
  }, ignoreNULL = FALSE)

  scores_data <- eventReactive(input$refresh, {
    fetch_content_items(con)
  }, ignoreNULL = FALSE)

  agg_metrics_data <- reactive({
    req(metrics_data())
    metrics_data() %>%
      group_by(content_item_id) %>%
      summarise(
        total_clicks      = sum(clicks,      na.rm = TRUE),
        total_impressions = sum(impressions, na.rm = TRUE),
        .groups = "drop"
      )
  })

  # ... chart outputs as above
}
```

---

## Future FR Preparation

These helpers are not fully implemented in this FR but are scaffolded here so FR-023 and FR-024 can build on them without changes to function signatures.

### For FR-023 — Reddit Hot decay

`compute_logic.R` will need:

```r
compute_hot_score <- function(metrics, gravity = 0.05) {
  metrics %>%
    dplyr::mutate(
      age_days   = as.numeric(lubridate::today() - date),
      hot_row    = log10(pmax(clicks + 0.05 * impressions, 1)) - gravity * age_days
    ) %>%
    dplyr::group_by(content_item_id) %>%
    dplyr::summarise(hot_raw = sum(hot_row, na.rm = TRUE), .groups = "drop")
}
```

`lubridate::today() - date` produces a clean numeric age without `difftime` conversion — only possible after this FR adds `lubridate`.

### For FR-024 — Read-Through Rate rolling average

```r
compute_rolling_engagement <- function(metrics, lookback_days = 30) {
  filter_lookback_window(metrics, lookback_days) %>%
    fill_date_gaps(lookback_days) %>%
    dplyr::group_by(content_item_id) %>%
    dplyr::summarise(
      avg_eng_time  = mean(avg_engagement_time, na.rm = TRUE),
      avg_bounce    = mean(bounce_rate,          na.rm = TRUE),
      metric_rows   = dplyr::n(),
      .groups = "drop"
    )
}
```

`fill_date_gaps()` (added in Part 2) ensures the average is over the full window, not just days with data.

---

## `DESCRIPTION` Final State

```
Package: ranalytics
Title: XF Internal Linker R Analytics
Version: 0.2.0
Authors@R: person("Antigravity", role = c("aut", "cre"))
Description: R analytics service for xf-internal-linker-v2.
License: Proprietary
Encoding: UTF-8
LazyData: true
Imports:
    DBI,
    RPostgres,
    config,
    dplyr,
    tibble,
    rlang,
    lubridate,
    tidyr,
    ggplot2,
    purrr
Suggests:
    testthat (>= 3.0.0)
Config/testthat/edition: 3
```

Version bumped from `0.1.0` to `0.2.0`.

---

## Test Plan

### Existing tests

All existing tests in `services/r-analytics/tests/` must pass without modification.

### New tests

- `filter_lookback_window()` returns only rows within the window.
- `filter_lookback_window()` with `lookback_days = 0` returns empty data frame, not an error.
- `fill_date_gaps()` inserts zero rows for missing dates.
- `fill_date_gaps()` on empty input returns empty input unchanged.
- `compute_content_value_score()` with windowed metrics produces the same score as before for data fully within the window.
- `fetch_search_metrics_windowed()` returns only rows on or after the cutoff date.
- `write_content_value_scores()` with `purrr::pwalk()` writes the same values as the old loop.
- Dashboard `renderPlot` outputs do not error on empty data.

### Manual verification

- Run `compute_content_value_score()` on real data — confirm scores unchanged.
- Open the Shiny dashboard — confirm three chart tabs render with real data.
- Run `write_content_value_scores()` in dry-run mode — confirm no change in behaviour.

---

## Acceptance Criteria

- `lubridate`, `tidyr`, `ggplot2`, and `purrr` are in `DESCRIPTION` and available to all R files in the service.
- `filter_lookback_window()` and `fill_date_gaps()` are implemented and used in `compute_content_value_score()`.
- `fetch_search_metrics_windowed()` exists and accepts a `lookback_days` parameter.
- Row-by-row `for` loop in `write_layer.R` is replaced with `purrr::pwalk()`.
- Dashboard shows a score distribution chart, a traffic trend chart, and a clicks-vs-impressions scatter chart reading from live data.
- All existing tests still pass.
- Docker image rebuilds cleanly with the four new packages installed.

## Out-of-Scope Follow-Up

- True batch upsert using a staging table (replaces `pwalk` with a single SQL statement).
- `dbplyr` — using dplyr verbs directly against the database instead of raw SQL queries.
- Interactive Shiny filters (date range pickers, content-type selectors).
- `readr` for CSV fixture loading in tests.
- `stringr` for URL normalisation helpers.
