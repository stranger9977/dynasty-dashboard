library(testthat)
library(arrow)
library(dplyr)

# Resolve models.R relative to this test file so the test works whether
# invoked from repo root, tests_R dir, or via testthat::test_dir.
.models_path <- function() {
  here <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) NULL)
  candidates <- c(
    if (!is.null(here)) file.path(here, "..", "models.R"),
    "analysis/late_round_eval/models.R",
    "../models.R"
  )
  for (p in candidates) {
    if (!is.null(p) && file.exists(p)) return(normalizePath(p))
  }
  stop("Cannot locate models.R from ", getwd())
}
source(.models_path(), local = TRUE)

set.seed(42)
fake_df <- tibble::tibble(
  position = sample(c("WR", "RB"), 100, replace = TRUE),
  age = runif(100, 21, 25),
  draft_pick = sample(1:262, 100, replace = TRUE),
  canonical_tier = factor(sample(c("Dart Throw","Depth","Flex","Starter","Elite"), 100, replace = TRUE),
                          levels = c("Dart Throw","Depth","Flex","Starter","Elite"), ordered = TRUE),
  best_ffppg = pmax(0, rnorm(100, 8, 5))
)

test_that("fit_regression returns baseline and guide models with metrics", {
  res <- fit_regression(fake_df |> filter(position == "WR"))
  expect_true("baseline" %in% names(res))
  expect_true("guide" %in% names(res))
  expect_true("metrics" %in% names(res))
  expect_true(all(c("adj_r2_baseline", "adj_r2_guide", "delta_r2",
                    "mae_baseline", "mae_guide",
                    "rmse_baseline", "rmse_guide",
                    "f_test_p") %in% names(res$metrics)))
})

test_that("fit_classification returns kappa and AUC", {
  res <- fit_classification(fake_df |> filter(position == "RB"))
  expect_true("metrics" %in% names(res))
  for (m in c("acc_baseline","acc_guide","kappa_baseline","kappa_guide",
              "macro_auc_baseline","macro_auc_guide")) {
    expect_true(m %in% names(res$metrics))
  }
})

test_that("compute_threshold_auc returns AUC for hit and elite thresholds", {
  preds <- runif(100)
  res <- compute_threshold_auc(preds, fake_df$best_ffppg)
  expect_true("auc_hit" %in% names(res))
  expect_true("auc_elite" %in% names(res))
  expect_true(res$auc_hit >= 0 & res$auc_hit <= 1)
})
