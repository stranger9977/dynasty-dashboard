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

test_that("canonicalize_college strips mascots and handles synonyms", {
  expect_equal(canonicalize_college("Alabama Crimson Tide"), "Alabama")
  expect_equal(canonicalize_college("Georgia Bulldogs"), "Georgia")
  expect_equal(canonicalize_college("Ohio State Buckeyes"), "Ohio State")
  expect_equal(canonicalize_college("Louisiana State Tigers"), "LSU")
  expect_equal(canonicalize_college("Southern California"), "USC")
  expect_equal(canonicalize_college("Ole Miss"), "Mississippi")
  expect_equal(canonicalize_college("Notre Dame Fighting Irish"), "Notre Dame")
  expect_equal(canonicalize_college("Iowa State Cyclones"), "Iowa State")
  expect_equal(canonicalize_college("Georgia"), "Georgia")  # already canonical
})

test_that("p5_flag works with mascot-bearing names", {
  expect_true(p5_flag("Alabama Crimson Tide", 2023))
  expect_true(p5_flag("Ohio State Buckeyes", 2024))
  expect_true(p5_flag("Louisiana State Tigers", 2023))
  expect_true(p5_flag("Notre Dame Fighting Irish", 2024))
})

test_that("assign_production_tier buckets FFPPG into canonical tiers", {
  result <- assign_production_tier(c(NA, 0, 2.5, 3.0, 5, 7, 10, 12, 15, 17.9, 18, 22))
  expect_equal(as.character(result),
               c(NA, "Dart Throw", "Dart Throw", "Depth", "Depth", "Flex",
                 "Flex", "Starter", "Starter", "Starter", "Elite", "Elite"))
  expect_true(is.ordered(result))
  expect_equal(levels(result), c("Dart Throw", "Depth", "Flex", "Starter", "Elite"))
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
