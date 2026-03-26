library(testthat)
library(dplyr)
library(tibble)

# Source the logic
source("/app/R/compute_logic.R")

test_that("compute_content_value_score handles empty input", {
  metrics <- tibble()
  content <- tibble(id = 1, title = "Test")
  
  res <- compute_content_value_score(metrics, content)
  expect_equal(res$new_score, 0.5)
})

test_that("compute_content_value_score clamps values to [0, 1]", {
  # Mock high metrics
  metrics <- tibble(
    content_item_id = 1,
    clicks = 1000,
    impressions = 10000,
    page_views = 5000
  )
  content <- tibble(id = 1, title = "Viral Post")
  
  res <- compute_content_value_score(metrics, content)
  expect_true(res$new_score <= 1.0)
  expect_true(res$new_score >= 0.0)
})

test_that("tune_ranking_weights respects max delta", {
  suggestions <- tibble(status = "applied")
  current <- 0.2
  
  new_w <- tune_ranking_weights(suggestions, current)
  expect_true(abs(new_w - current) <= 0.05)
})
