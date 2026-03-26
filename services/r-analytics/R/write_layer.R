#' Safe Write Layer
#' @import DBI

write_content_value_scores <- function(con, scores_df) {
  dry_run <- config::get()$settings$dry_run
  
  if (dry_run) {
    message("DRY_RUN=TRUE: Skipping write to content_contentitem.content_value_score.")
    # Report what would have happened
    print(head(scores_df %>% select(id, title, new_score)))
    return(TRUE)
  }
  
  message("DRY_RUN=FALSE: Writing scores to database.")
  
  # Validate ranges
  if (any(scores_df$new_score < 0 | scores_df$new_score > 1)) {
    stop("Value range violation: content_value_score must be in [0, 1].")
  }
  
  # Perform bounded writes
  for (i in 1:nrow(scores_df)) {
    row <- scores_df[i, ]
    dbExecute(
      con,
      "UPDATE content_contentitem SET content_value_score = $1 WHERE id = $2",
      params = list(row$new_score, row$id)
    )
  }
  
  return(TRUE)
}

write_app_setting_weight <- function(con, key, new_weight) {
  dry_run <- config::get()$settings$dry_run
  
  # Whitelist approved ML weight keys
  approved_keys <- c("ga4_gsc.ranking_weight", "ml.ga4_gsc_ranking_weight")
  if (!(key %in% approved_keys)) {
    stop("Forbidden write attempt to key: ", key)
  }
  
  if (dry_run) {
    message("DRY_RUN=TRUE: Skipping write to core_appsetting.value for key: ", key)
    message("Proposed weight: ", new_weight)
    return(TRUE)
  }
  
  message("DRY_RUN=FALSE: Updating app setting weight.")
  
  # Validate range
  if (new_weight < 0 || new_weight > 1) {
    stop("Value range violation: ranking_weight must be in [0, 1].")
  }
  
  # Perform update
  dbExecute(
    con,
    "UPDATE core_appsetting SET value = $1 WHERE key = $2",
    params = list(as.character(new_weight), key)
  )
  
  return(TRUE)
}
