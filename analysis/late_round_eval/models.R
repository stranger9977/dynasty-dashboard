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

# Tier-vs-tier evaluation. Compares a predicted tier (his canonical_tier OR
# a baseline_tier derived from age + log(draft_pick)) against the
# production_tier defined by FFPG cutoffs (18 / 12 / 7 / 3).
#
# Returns:
#   - confusion (5x5 table: rows = true production_tier, cols = predicted)
#   - per_tier (precision/recall/f1 per tier)
#   - overall (accuracy, weighted F1, quadratic kappa, off-by-one rate)
fit_tier_vs_tier <- function(predicted_tier, production_tier) {
  tier_levels <- c("Dart Throw", "Depth", "Flex", "Starter", "Elite")
  pred  <- factor(as.character(predicted_tier), levels = tier_levels, ordered = TRUE)
  truth <- factor(as.character(production_tier), levels = tier_levels, ordered = TRUE)

  ok <- !is.na(pred) & !is.na(truth)
  pred <- pred[ok]; truth <- truth[ok]
  n <- length(pred)

  confusion <- table(truth = truth, pred = pred)

  per_tier <- lapply(tier_levels, function(cls) {
    tp <- sum(pred == cls & truth == cls)
    fp <- sum(pred == cls & truth != cls)
    fn <- sum(pred != cls & truth == cls)
    support <- sum(truth == cls)
    prec <- if (tp + fp == 0) NA_real_ else tp / (tp + fp)
    rec  <- if (tp + fn == 0) NA_real_ else tp / (tp + fn)
    f1   <- if (is.na(prec) || is.na(rec) || (prec + rec) == 0) NA_real_
            else 2 * prec * rec / (prec + rec)
    tibble(tier = cls, support = support, precision = prec, recall = rec, f1 = f1)
  }) |> bind_rows()
  per_tier$tier <- factor(per_tier$tier, levels = tier_levels, ordered = TRUE)

  # Overall metrics
  acc <- sum(pred == truth) / n
  off_by_one <- sum(abs(as.integer(pred) - as.integer(truth)) <= 1) / n
  wf1 <- weighted_f1(truth, pred, tier_levels)
  kappa <- quadratic_weighted_kappa(truth, pred, tier_levels)

  overall <- list(n = n, accuracy = acc, off_by_one_rate = off_by_one,
                  weighted_f1 = wf1, quadratic_kappa = kappa)

  list(confusion = confusion, per_tier = per_tier, overall = overall)
}

# Bucket a continuous prediction (from a baseline regression) into the same
# FFPG-defined production tiers so we can compare apples-to-apples to JJ's
# tier calls. Falls back to the same cutoffs as `assign_production_tier`.
predict_tier_from_lm <- function(model, newdata) {
  pred_ffppg <- predict(model, newdata = newdata)
  # Reuse cutoffs by calling out to data_pipeline.R's helper (already sourced)
  assign_production_tier(pred_ffppg)
}


# Build a percentile-rank baseline score (0-100) from `lm(best_ffppg ~ age +
# log(draft_pick))`, fit and ranked WITHIN each position. Returns a tibble:
#   player_id, position, baseline_score (0-100), zap_score (carried through),
#   best_ffppg, production_tier
# Use this to compare JJ's ZAP score and the draft-capital baseline on the
# same 0-100 scale.
build_score_table <- function(eval_df) {
  out <- list()
  for (pos in c("WR", "RB")) {
    df <- eval_df |> dplyr::filter(position == pos,
                                    !is.na(best_ffppg), !is.na(age), !is.na(draft_pick))
    df$log_capital <- log(df$draft_pick)
    m <- lm(best_ffppg ~ age + log_capital, data = df)
    df$baseline_pred_ffppg <- predict(m)
    # Percentile-rank within position. percent_rank returns 0-1; scale to 0-100.
    df$baseline_score <- 100 * dplyr::percent_rank(df$baseline_pred_ffppg)
    out[[pos]] <- df |>
      dplyr::select(player_id, name, position, guide_year, draft_round, draft_pick,
                    age, best_ffppg, production_tier, canonical_tier,
                    zap_score, baseline_pred_ffppg, baseline_score)
  }
  dplyr::bind_rows(out)
}


# Quadrant classification on aligned (0-100) scores: bisect at 50.
# Returns the score table with a `quadrant` column:
#   high_zap_high_baseline  = both like the player ("consensus hit")
#   high_zap_low_baseline   = JJ sleeper (he likes, draft capital doesn't)
#   low_zap_high_baseline   = JJ fade (draft capital likes, he doesn't)
#   low_zap_low_baseline    = consensus pass
classify_quadrants <- function(scored, zap_threshold = 50, baseline_threshold = 50) {
  scored |>
    dplyr::filter(!is.na(zap_score)) |>
    dplyr::mutate(
      high_zap = zap_score >= zap_threshold,
      high_base = baseline_score >= baseline_threshold,
      quadrant = dplyr::case_when(
         high_zap &  high_base ~ "Consensus hit",
         high_zap & !high_base ~ "JJ sleeper",
        !high_zap &  high_base ~ "JJ fade",
        TRUE                   ~ "Consensus pass"
      )
    )
}


# Correlation of each score with continuous best_ffppg, per position. Also
# returns the slope of best_ffppg on each score for interpretability.
score_correlations <- function(scored) {
  out <- list()
  for (pos in c("WR", "RB")) {
    df <- scored |> dplyr::filter(position == pos)
    df_zap <- df |> dplyr::filter(!is.na(zap_score))
    out[[pos]] <- tibble(
      position = pos,
      n_total = nrow(df), n_with_zap = nrow(df_zap),
      cor_baseline = cor(df$baseline_score, df$best_ffppg),
      cor_zap = if (nrow(df_zap) >= 5) cor(df_zap$zap_score, df_zap$best_ffppg)
                else NA_real_,
      slope_baseline = coef(lm(best_ffppg ~ baseline_score, data = df))[2],
      slope_zap = if (nrow(df_zap) >= 5)
                    coef(lm(best_ffppg ~ zap_score, data = df_zap))[2]
                  else NA_real_
    )
  }
  dplyr::bind_rows(out)
}


# JJ-vs-baseline disagreement analysis.
#
# Operational sleeper definition: a "JJ bump" is when JJ's ZAP score exceeds
# the draft-capital + age baseline score on the same 0-100 scale. We bucket
# the gap (zap - baseline) and report outcome distributions.
#
# Returns a tibble of per-player gaps + a summary by bump magnitude bucket.
jj_bump_analysis <- function(scored, late_round_only = FALSE) {
  df <- scored |>
    dplyr::filter(!is.na(zap_score), !is.na(baseline_score)) |>
    dplyr::mutate(
      bump = zap_score - baseline_score,
      bump_bucket = dplyr::case_when(
        bump >=  30 ~ "Big JJ bump (+30 or more)",
        bump >=  10 ~ "Moderate JJ bump (+10 to +30)",
        bump >  -10 ~ "Neutral (within +-10)",
        bump >  -30 ~ "Moderate JJ fade (-10 to -30)",
        TRUE        ~ "Big JJ fade (-30 or worse)"
      ),
      bump_bucket = factor(bump_bucket, levels = c(
        "Big JJ bump (+30 or more)",
        "Moderate JJ bump (+10 to +30)",
        "Neutral (within +-10)",
        "Moderate JJ fade (-10 to -30)",
        "Big JJ fade (-30 or worse)"
      ))
    )
  if (late_round_only) {
    df <- df |> dplyr::filter(draft_round %in% c("day-3", "UDFA"))
  }

  summary <- df |>
    dplyr::group_by(position, bump_bucket) |>
    dplyr::summarise(
      n = dplyr::n(),
      mean_ffppg = mean(best_ffppg),
      starter_plus_rate = mean(production_tier >= "Starter"),
      elite_rate = mean(production_tier == "Elite"),
      bust_rate = mean(production_tier == "Dart Throw"),
      .groups = "drop"
    )

  list(detail = df, summary = summary)
}


# Calibration: split each score into deciles, report mean best_ffppg and
# fraction in each production_tier per decile. `score_col` is the column name
# to bucket on ("baseline_score" or "zap_score").
score_calibration <- function(scored, score_col, position_filter = NULL,
                              n_buckets = 10) {
  df <- scored
  if (!is.null(position_filter)) df <- df |> dplyr::filter(position == position_filter)
  df <- df |> dplyr::filter(!is.na(.data[[score_col]]))
  if (nrow(df) == 0) return(tibble())
  df$bucket <- ntile(df[[score_col]], n_buckets)
  df |>
    dplyr::group_by(bucket) |>
    dplyr::summarise(
      n = dplyr::n(),
      score_min = min(.data[[score_col]]),
      score_max = max(.data[[score_col]]),
      mean_ffppg = mean(best_ffppg),
      starter_plus_rate = mean(production_tier >= "Starter"),
      elite_rate = mean(production_tier == "Elite"),
      bust_rate = mean(production_tier == "Dart Throw"),
      .groups = "drop"
    )
}

# Full per-position eval: predicted_tier (his canonical_tier) and baseline_tier
# (from age + log(draft_pick) -> FFPG -> bucket) both compared to production_tier.
run_tier_eval <- function(eval_df) {
  out <- list()
  for (pos in c("WR", "RB")) {
    df <- eval_df |> dplyr::filter(position == pos,
                                    !is.na(production_tier),
                                    !is.na(canonical_tier),
                                    !is.na(age), !is.na(draft_pick))
    df$log_capital <- log(df$draft_pick)
    baseline_lm <- lm(best_ffppg ~ age + log_capital, data = df)
    df$baseline_tier <- predict_tier_from_lm(baseline_lm, df)

    his_eval <- fit_tier_vs_tier(df$canonical_tier, df$production_tier)
    baseline_eval <- fit_tier_vs_tier(df$baseline_tier, df$production_tier)

    out[[pos]] <- list(df = df, his = his_eval, baseline = baseline_eval,
                       baseline_lm = baseline_lm)
  }
  out
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


# ZAP-score-as-continuous-input comparison.
# Restricted to 2024+ classes since 2022/2023 cheatsheets did not publish
# per-player scores. Fits four nested models per position:
#   baseline   : best_ffppg ~ age + log(draft_pick)
#   +tier      : + canonical_tier (categorical, 5 levels)
#   +zap       : + zap_score (continuous, 0-100)
#   +both      : + canonical_tier + zap_score
#
# Returns a list of per-position results, each containing the four fits, a
# tidy metrics table, and threshold AUCs.
fit_zap_comparison <- function(eval_df) {
  df_all <- eval_df |>
    dplyr::filter(!is.na(zap_score), !is.na(best_ffppg),
                  !is.na(age), !is.na(draft_pick), !is.na(canonical_tier))
  out <- list()
  for (pos in c("WR", "RB")) {
    df <- df_all |> dplyr::filter(position == pos)
    if (nrow(df) < 10) {
      out[[pos]] <- list(error = sprintf("insufficient data (n=%d)", nrow(df)))
      next
    }
    df$log_capital <- log(df$draft_pick)

    m_baseline <- lm(best_ffppg ~ age + log_capital, data = df)
    m_tier     <- lm(best_ffppg ~ age + log_capital + canonical_tier, data = df)
    m_zap      <- lm(best_ffppg ~ age + log_capital + zap_score, data = df)
    m_both     <- lm(best_ffppg ~ age + log_capital + canonical_tier + zap_score, data = df)

    metrics_row <- function(name, m) {
      pred <- predict(m)
      list(
        model = name,
        n = nrow(df),
        adj_r2 = summary(m)$adj.r.squared,
        mae    = mean(abs(df$best_ffppg - pred)),
        rmse   = sqrt(mean((df$best_ffppg - pred)^2)),
        auc_hit   = compute_threshold_auc(pred, df$best_ffppg)$auc_hit,
        auc_elite = compute_threshold_auc(pred, df$best_ffppg)$auc_elite
      )
    }

    metrics <- bind_rows(
      metrics_row("baseline (age + log capital)", m_baseline),
      metrics_row("+ canonical_tier",             m_tier),
      metrics_row("+ zap_score",                  m_zap),
      metrics_row("+ canonical_tier + zap_score", m_both)
    )

    # Nested F-tests vs baseline
    f_tier <- anova(m_baseline, m_tier)$`Pr(>F)`[2]
    f_zap  <- anova(m_baseline, m_zap)$`Pr(>F)`[2]
    f_both <- anova(m_baseline, m_both)$`Pr(>F)`[2]
    # Marginal test: does zap add to a model that already has tier?
    f_zap_over_tier <- anova(m_tier, m_both)$`Pr(>F)`[2]

    out[[pos]] <- list(
      df = df,
      metrics = metrics,
      f_tests = list(
        tier_vs_baseline      = f_tier,
        zap_vs_baseline       = f_zap,
        both_vs_baseline      = f_both,
        zap_adds_over_tier    = f_zap_over_tier
      ),
      fits = list(baseline = m_baseline, tier = m_tier, zap = m_zap, both = m_both)
    )
  }
  out
}
