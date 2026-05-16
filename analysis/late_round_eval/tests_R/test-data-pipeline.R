library(testthat)
library(arrow)
library(dplyr)

# Resolve data_pipeline.R relative to this test file so the test works whether
# invoked from repo root, the tests_R dir, or via testthat::test_dir.
.pipeline_path <- function() {
  here <- tryCatch(
    dirname(sys.frame(1)$ofile),
    error = function(e) NULL
  )
  candidates <- c(
    if (!is.null(here)) file.path(here, "..", "data_pipeline.R"),
    "analysis/late_round_eval/data_pipeline.R",
    "../data_pipeline.R",
    file.path(dirname(getwd()), "data_pipeline.R")
  )
  for (p in candidates) {
    if (!is.null(p) && file.exists(p)) return(normalizePath(p))
  }
  stop("Cannot locate data_pipeline.R from working dir ", getwd())
}
source(.pipeline_path(), local = TRUE)

test_that("normalize_name strips Jr/Sr/punct and lowercases", {
  expect_equal(normalize_name("Ja'Marr Chase Jr."), "jamarr chase")
  expect_equal(normalize_name("D.J. Moore"), "dj moore")
  expect_equal(normalize_name("  Pete Carroll  "), "pete carroll")
})

test_that("classify_draft_round buckets correctly", {
  expect_equal(classify_draft_round(1), "1")
  expect_equal(classify_draft_round(2), "2")
  expect_equal(classify_draft_round(3), "3")
  expect_equal(classify_draft_round(4), "day-3")
  expect_equal(classify_draft_round(7), "day-3")
  expect_equal(classify_draft_round(NA), "UDFA")
})

test_that("p5_flag handles realignment", {
  expect_true(p5_flag("Georgia", 2023))            # SEC, always P5
  expect_true(p5_flag("Oregon", 2023))             # was Pac-12, P5
  expect_true(p5_flag("Oregon", 2024))             # moved to Big Ten, still P5
  expect_false(p5_flag("Oregon State", 2024))      # stranded in rump Pac-12
  expect_false(p5_flag("Washington State", 2024))  # stranded in rump Pac-12
  expect_true(p5_flag("Notre Dame", 2024))         # independent, treated as P5
  expect_false(p5_flag("Appalachian State", 2024)) # Sun Belt, never P5
})

test_that("compute_best_ffppg picks max season FFPPG in Y1-Y3", {
  stats <- tibble::tribble(
    ~player_id, ~season, ~fantasy_points_ppr, ~games,
    "P1",       2022,    150,                 17,   # 8.82 PPG
    "P1",       2023,    200,                 16,   # 12.5 PPG  <- max
    "P1",       2024,    100,                 12,   # 8.33 PPG
    "P2",       2025,    50,                  10,   # 5.0 PPG
  )
  result <- compute_best_ffppg(stats, draft_year_lookup = c(P1 = 2022, P2 = 2025), max_years = 3)
  expect_equal(round(result$best_ffppg[result$player_id == "P1"], 2), 12.50)
  expect_equal(round(result$best_ffppg[result$player_id == "P2"], 2), 5.00)
})
