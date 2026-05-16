# Late Round Prospect Guide — Modeling
# Per-position regression and classification: baseline (age + log(draft_pick))
# vs. baseline + his canonical tier.

library(tidyverse)
library(MASS)
library(pROC)

# dplyr::select gets masked by MASS::select — re-export explicitly to avoid surprises
select <- dplyr::select

fit_regression <- function(df) {
  df <- df |> dplyr::filter(!is.na(best_ffppg), !is.na(age), !is.na(draft_pick), !is.na(canonical_tier))
  df$log_capital <- log(df$draft_pick)
  baseline <- lm(best_ffppg ~ age + log_capital, data = df)
  guide    <- lm(best_ffppg ~ age + log_capital + canonical_tier, data = df)

  pred_b <- predict(baseline)
  pred_g <- predict(guide)

  metrics <- list(
    n = nrow(df),
    adj_r2_baseline = summary(baseline)$adj.r.squared,
    adj_r2_guide    = summary(guide)$adj.r.squared,
    delta_r2        = summary(guide)$adj.r.squared - summary(baseline)$adj.r.squared,
    mae_baseline    = mean(abs(df$best_ffppg - pred_b)),
    mae_guide       = mean(abs(df$best_ffppg - pred_g)),
    rmse_baseline   = sqrt(mean((df$best_ffppg - pred_b)^2)),
    rmse_guide      = sqrt(mean((df$best_ffppg - pred_g)^2)),
    f_test_p        = anova(baseline, guide)$`Pr(>F)`[2]
  )

  list(baseline = baseline, guide = guide, metrics = metrics, df = df,
       pred_baseline = pred_b, pred_guide = pred_g)
}

quadratic_weighted_kappa <- function(actual, predicted, levels) {
  k <- length(levels)
  a <- factor(actual, levels = levels)
  p <- factor(predicted, levels = levels)
  o <- table(a, p)
  rs <- rowSums(o); cs <- colSums(o); n <- sum(o)
  e <- outer(rs, cs) / n
  w <- outer(seq_len(k), seq_len(k), function(i, j) (i - j)^2 / (k - 1)^2)
  1 - sum(w * o) / sum(w * e)
}

weighted_f1 <- function(truth, pred, levels) {
  f1s <- c(); weights <- c()
  for (cls in levels) {
    tp <- sum(pred == cls & truth == cls)
    fp <- sum(pred == cls & truth != cls)
    fn <- sum(pred != cls & truth == cls)
    prec <- if (tp + fp == 0) 0 else tp / (tp + fp)
    rec  <- if (tp + fn == 0) 0 else tp / (tp + fn)
    f1 <- if (prec + rec == 0) 0 else 2 * prec * rec / (prec + rec)
    f1s <- c(f1s, f1)
    weights <- c(weights, sum(truth == cls))
  }
  if (sum(weights) == 0) return(NA_real_)
  sum(f1s * weights) / sum(weights)
}

fit_classification <- function(df) {
  df <- df |> dplyr::filter(!is.na(best_ffppg), !is.na(age), !is.na(draft_pick), !is.na(canonical_tier))
  df$log_capital <- log(df$draft_pick)
  tier_levels <- c("Dart Throw","Depth","Flex","Starter","Elite")

  baseline_clf <- tryCatch(
    polr(canonical_tier ~ age + log_capital, data = df, Hess = TRUE),
    error = function(e) nnet::multinom(canonical_tier ~ age + log_capital, data = df, trace = FALSE)
  )

  baseline_pred_class <- predict(baseline_clf, df, type = "class")
  baseline_prob <- predict(baseline_clf, df, type = "probs")
  if (is.vector(baseline_prob)) baseline_prob <- t(as.matrix(baseline_prob))

  # Compare on character level so ordered vs unordered factors don't blow up
  truth_chr <- as.character(df$canonical_tier)
  baseline_pred_chr <- as.character(baseline_pred_class)

  guide_pred_class <- df$canonical_tier
  guide_ordinal_score <- as.integer(df$canonical_tier)

  macro_auc <- function(prob_mat, ordinal_score_alt = NULL) {
    aucs <- c()
    for (cls in tier_levels) {
      truth <- as.integer(df$canonical_tier == cls)
      if (length(unique(truth)) < 2) next
      if (!is.null(ordinal_score_alt)) {
        rank_target <- match(cls, tier_levels)
        score <- -abs(as.integer(df$canonical_tier) - rank_target)
      } else {
        score <- prob_mat[, cls]
      }
      aucs <- c(aucs, as.numeric(pROC::auc(pROC::roc(truth, score, quiet = TRUE))))
    }
    if (length(aucs) == 0) return(NA_real_)
    mean(aucs, na.rm = TRUE)
  }

  metrics <- list(
    n = nrow(df),
    acc_baseline   = mean(baseline_pred_chr == truth_chr),
    acc_guide      = mean(as.character(guide_pred_class) == truth_chr),  # = 1.0 trivially
    weighted_f1_baseline = weighted_f1(truth_chr, baseline_pred_chr, tier_levels),
    weighted_f1_guide    = 1.0,  # trivially since he predicts his own label
    kappa_baseline = quadratic_weighted_kappa(truth_chr, baseline_pred_chr, tier_levels),
    kappa_guide    = NA_real_,
    macro_auc_baseline = macro_auc(baseline_prob),
    macro_auc_guide    = macro_auc(NULL, ordinal_score_alt = guide_ordinal_score)
  )

  confusion_baseline <- table(
    truth = factor(truth_chr, levels = tier_levels),
    pred  = factor(baseline_pred_chr, levels = tier_levels)
  )

  list(baseline = baseline_clf, metrics = metrics,
       confusion_baseline = confusion_baseline, df = df,
       baseline_prob = baseline_prob)
}

compute_threshold_auc <- function(pred_numeric, truth_ffppg) {
  hit <- as.integer(truth_ffppg >= 10)
  elite <- as.integer(truth_ffppg >= 15)
  auc_hit <- if (length(unique(hit)) == 2)
    as.numeric(pROC::auc(pROC::roc(hit, pred_numeric, quiet = TRUE))) else NA_real_
  auc_elite <- if (length(unique(elite)) == 2)
    as.numeric(pROC::auc(pROC::roc(elite, pred_numeric, quiet = TRUE))) else NA_real_
  list(auc_hit = auc_hit, auc_elite = auc_elite)
}

run_per_position_models <- function(eval_df) {
  out <- list()
  for (pos in c("WR", "RB")) {
    df_pos <- eval_df |> dplyr::filter(position == pos)
    reg <- fit_regression(df_pos)
    clf <- fit_classification(df_pos)
    auc_b <- compute_threshold_auc(reg$pred_baseline, reg$df$best_ffppg)
    auc_g <- compute_threshold_auc(as.integer(reg$df$canonical_tier), reg$df$best_ffppg)
    out[[pos]] <- list(
      regression = reg,
      classification = clf,
      threshold_auc_baseline = auc_b,
      threshold_auc_guide = auc_g
    )
  }
  out
}
