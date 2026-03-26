#' Data Fetch Layer
#' @import dplyr tibble

fetch_search_metrics <- function(con) {
  query <- "SELECT * FROM analytics_searchmetric"
  empty <- tibble(
    id = integer(),
    content_item_id = integer(),
    date = Date(),
    source = character(),
    impressions = integer(),
    clicks = integer(),
    ctr = numeric(),
    average_position = numeric(),
    query = character(),
    page_views = integer(),
    sessions = integer(),
    avg_engagement_time = numeric(),
    bounce_rate = numeric()
  )
  safe_query(con, query, empty_types = empty)
}

fetch_content_items <- function(con) {
  query <- "SELECT id, content_id, content_type, title, content_value_score, xf_post_id FROM content_contentitem"
  empty <- tibble(
    id = integer(),
    content_id = integer(),
    content_type = character(),
    title = character(),
    content_value_score = numeric(),
    xf_post_id = integer()
  )
  safe_query(con, query, empty_types = empty)
}

fetch_suggestions <- function(con) {
  query <- "SELECT suggestion_id, destination_id, host_id, score_final, score_ga4_gsc, status FROM suggestions_suggestion"
  empty <- tibble(
    suggestion_id = character(),
    destination_id = integer(),
    host_id = integer(),
    score_final = numeric(),
    score_ga4_gsc = numeric(),
    status = character()
  )
  safe_query(con, query, empty_types = empty)
}

fetch_app_settings <- function(con) {
  query <- "SELECT key, value, value_type FROM core_appsetting"
  empty <- tibble(
    key = character(),
    value = character(),
    value_type = character()
  )
  safe_query(con, query, empty_types = empty)
}
