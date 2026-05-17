# Chart functions for late round guide eval. Each returns a ggplot or list of plots.

library(ggplot2)
library(patchwork)
library(scales)
library(dplyr)
library(tidyr)
library(ggrepel)

CHART_DIR <- "analysis/late_round_eval/charts"
dir.create(CHART_DIR, recursive = TRUE, showWarnings = FALSE)

TIER_COLORS <- c(
  "Elite" = "#1a9850",
  "Starter" = "#91cf60",
  "Flex" = "#fee08b",
  "Depth" = "#fc8d59",
  "Dart Throw" = "#d73027"
)

save_chart <- function(plot, name, width = 8, height = 5, dpi = 150) {
  path <- file.path(CHART_DIR, paste0(name, ".png"))
  ggsave(path, plot, width = width, height = height, dpi = dpi)
  path
}

chart_coverage <- function(eval_df, harmonized_all) {
  # harmonized_all includes 2026; eval_df does not
  harmonized_all |>
    dplyr::filter(position %in% c("WR", "RB")) |>
    dplyr::count(guide_year, position, canonical_tier) |>
    ggplot(aes(x = factor(guide_year), y = n, fill = canonical_tier)) +
    geom_col() +
    facet_wrap(~position) +
    scale_fill_manual(values = TIER_COLORS) +
    labs(x = "Guide year", y = "Players", fill = "Canonical tier",
         title = "Coverage by year, position, and canonical tier") +
    theme_minimal()
}

chart_production_by_tier <- function(eval_df) {
  eval_df |>
    ggplot(aes(x = canonical_tier, y = best_ffppg, fill = canonical_tier)) +
    geom_boxplot(outlier.size = 0.6) +
    facet_wrap(~position) +
    scale_fill_manual(values = TIER_COLORS, guide = "none") +
    labs(x = "Canonical tier", y = "Best FFPPG (PPR, Y1-Y3)",
         title = "Realized production by canonical tier") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 30, hjust = 1))
}

chart_confusion_matrix <- function(confusion, title) {
  df <- as.data.frame(confusion)
  ggplot(df, aes(x = pred, y = truth, fill = Freq)) +
    geom_tile() +
    geom_text(aes(label = Freq), color = "white") +
    scale_fill_gradient(low = "#cccccc", high = "#08519c") +
    labs(title = title, x = "Predicted tier", y = "True tier") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 30, hjust = 1))
}

chart_slice_heatmap <- function(eval_df) {
  # Per-slice delta R^2 — uses fit_regression from models.R (must be sourced first)
  slices <- expand.grid(
    position = c("WR", "RB"),
    draft_round = c("1","2","3","day-3","UDFA"),
    p5_flag = c(TRUE, FALSE),
    stringsAsFactors = FALSE
  )
  slices$delta_r2 <- NA_real_
  for (i in seq_len(nrow(slices))) {
    sub <- eval_df |>
      dplyr::filter(position == slices$position[i],
                    draft_round == slices$draft_round[i],
                    p5_flag == slices$p5_flag[i])
    if (nrow(sub) < 8) next
    res <- tryCatch(fit_regression(sub), error = function(e) NULL)
    if (!is.null(res)) slices$delta_r2[i] <- res$metrics$delta_r2
  }
  slices$slice <- paste(slices$draft_round,
                        ifelse(slices$p5_flag, "P5", "non-P5"))
  ggplot(slices, aes(x = slice, y = position, fill = delta_r2)) +
    geom_tile() +
    geom_text(aes(label = ifelse(is.na(delta_r2), "—", sprintf("%.2f", delta_r2))),
              size = 3) +
    scale_fill_gradient2(low = "#d73027", mid = "#ffffbf", high = "#1a9850",
                         midpoint = 0, na.value = "#cccccc") +
    labs(title = "Slice heatmap: deltaR^2 of guide model over baseline",
         x = "Slice", y = "Position", fill = "ΔR²") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 30, hjust = 1))
}

chart_score_scatter <- function(scored, label_top_n = 5) {
  df <- scored |> dplyr::filter(!is.na(jj_score), !is.na(baseline_score))
  df$is_late <- df$draft_round %in% c("day-3", "UDFA")
  df$bump <- df$jj_score - df$baseline_score

  # Label the top N most-positive (JJ-bumps) and top N most-negative (JJ-fades)
  # per position panel.
  label_df <- df |>
    dplyr::group_by(position) |>
    dplyr::mutate(rank_pos = dplyr::row_number(dplyr::desc(bump)),
                  rank_neg = dplyr::row_number(bump)) |>
    dplyr::filter(rank_pos <= label_top_n | rank_neg <= label_top_n) |>
    dplyr::ungroup()

  quadrant_labels <- tibble::tribble(
    ~x,  ~y,  ~hjust, ~vjust, ~label,
     2, 100,  0,      1,      "JJ sleeper\n(he likes,\ndraft capital doesn't)",
    99, 100,  1,      1,      "Consensus hit\n(both bullish)",
     2,   2,  0,      0,      "Consensus pass\n(both bearish)",
    99,   2,  1,      0,      "JJ fade\n(draft capital likes,\nhe doesn't)"
  )

  ggplot(df, aes(x = baseline_score, y = jj_score, color = production_tier)) +
    geom_abline(slope = 1, intercept = 0, linetype = "dashed", color = "gray60") +
    geom_point(aes(shape = is_late), size = 2.5, alpha = 0.85) +
    ggrepel::geom_text_repel(
      data = label_df,
      aes(label = name),
      inherit.aes = TRUE,
      size = 2.8, max.overlaps = 30, seed = 1,
      box.padding = 0.3, point.padding = 0.2, segment.alpha = 0.5,
      show.legend = FALSE
    ) +
    geom_text(data = quadrant_labels,
              aes(x = x, y = y, label = label, hjust = hjust, vjust = vjust),
              inherit.aes = FALSE,
              size = 3, color = "gray35", fontface = "italic",
              lineheight = 0.9) +
    facet_wrap(~position) +
    scale_color_manual(values = TIER_COLORS, drop = FALSE) +
    scale_shape_manual(values = c(`FALSE` = 16, `TRUE` = 17),
                       labels = c(`FALSE` = "early-round", `TRUE` = "day-3 / UDFA"),
                       name = NULL) +
    coord_cartesian(xlim = c(0, 100), ylim = c(0, 100)) +
    labs(x = "Baseline score (age + log draft capital, 0-100 percentile within position)",
         y = "JJ score (0-100; ZAP for 2024-26, tier midpoint for 2022-23)",
         color = "Actual production tier",
         title = "Where JJ disagrees with draft capital — and who became what",
         subtitle = sprintf("Top %d JJ-bumps and top %d JJ-fades per position labeled.",
                            label_top_n, label_top_n)) +
    theme_minimal()
}

chart_ranking_lift <- function(ranking_out) {
  curves <- dplyr::bind_rows(
    ranking_out$WR$cumulative_lift,
    ranking_out$RB$cumulative_lift
  ) |>
    tidyr::pivot_longer(c(jj_cum_ffppg, baseline_cum_ffppg, optimal_cum_ffppg),
                        names_to = "method", values_to = "cum_ffppg") |>
    dplyr::mutate(method = dplyr::recode(method,
      jj_cum_ffppg       = "JJ ranking",
      baseline_cum_ffppg = "Draft capital + age ranking",
      optimal_cum_ffppg  = "Optimal (oracle)"
    ))

  ggplot(curves, aes(x = k, y = cum_ffppg, color = method, linetype = method)) +
    geom_line(linewidth = 0.9) +
    facet_wrap(~position, scales = "free") +
    scale_linetype_manual(values = c("JJ ranking" = "solid",
                                      "Draft capital + age ranking" = "solid",
                                      "Optimal (oracle)" = "22")) +
    scale_color_brewer(palette = "Set1") +
    labs(x = "Players drafted (in order of each method's ranking)",
         y = "Cumulative best FFPG of players drafted",
         color = NULL, linetype = NULL,
         title = "Dynasty drafting: cumulative production if you'd followed each ranking",
         subtitle = "Higher = picked better players first. Oracle = upper bound (sorted by actual production).") +
    theme_minimal() +
    theme(legend.position = "bottom")
}

chart_bump_outcomes <- function(bump_summary) {
  bump_summary |>
    ggplot(aes(x = bump_bucket, y = starter_plus_rate, fill = position)) +
    geom_col(position = position_dodge(width = 0.85), width = 0.8) +
    geom_text(aes(label = sprintf("n=%d", n)),
              position = position_dodge(width = 0.85), vjust = -0.4, size = 3) +
    scale_y_continuous(labels = scales::percent_format(accuracy = 1),
                       expand = expansion(mult = c(0, 0.15))) +
    scale_fill_brewer(palette = "Set1") +
    labs(x = NULL, y = "Starter+ rate (production tier >= Starter)",
         fill = "Position",
         title = "Outcome rate by JJ vs baseline disagreement",
         subtitle = "If JJ adds signal, the +bump buckets should hit at higher rates than the fades.") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 25, hjust = 1))
}

chart_lift_curve <- function(eval_df) {
  late <- eval_df |> dplyr::filter(draft_round %in% c("day-3", "UDFA"))
  if (nrow(late) < 5 || sum(late$hit_flag) == 0) {
    return(ggplot() + labs(title = "Insufficient late-round hit data"))
  }
  late <- late |> dplyr::arrange(desc(as.integer(canonical_tier)))
  late$cumulative_hits_by_him <- cumsum(late$hit_flag) / sum(late$hit_flag)
  late$cumulative_pct <- seq_len(nrow(late)) / nrow(late)

  late_baseline <- eval_df |>
    dplyr::filter(draft_round %in% c("day-3", "UDFA")) |>
    dplyr::arrange(draft_pick)
  late_baseline$cumulative_hits_by_capital <- cumsum(late_baseline$hit_flag) / sum(late_baseline$hit_flag)
  late_baseline$cumulative_pct <- seq_len(nrow(late_baseline)) / nrow(late_baseline)

  curves <- bind_rows(
    late |> dplyr::select(cumulative_pct, hits = cumulative_hits_by_him) |>
      mutate(method = "Guide tier rank"),
    late_baseline |> dplyr::select(cumulative_pct, hits = cumulative_hits_by_capital) |>
      mutate(method = "Draft capital rank")
  )

  ggplot(curves, aes(x = cumulative_pct, y = hits, color = method)) +
    geom_line(linewidth = 1) +
    geom_abline(linetype = "dashed", color = "gray") +
    labs(x = "Cumulative share of day-3+UDFA players evaluated",
         y = "Cumulative share of hits (FFPPG >= 10) captured",
         title = "Late-round lift: ranking by guide vs draft capital",
         color = NULL) +
    theme_minimal()
}
