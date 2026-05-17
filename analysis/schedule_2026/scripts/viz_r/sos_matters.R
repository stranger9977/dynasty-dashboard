## Does SoS actually matter? Historical retrospective scatter + decile residuals.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")
library(patchwork)

d <- read_parquet(file.path(PROJ_ROOT, "output/sos_matters/data.parquet"))

# Regression to extract residuals
fit <- lm(actual_wins ~ preseason_strength, data = d)
d$wins_residual <- residuals(fit)

# Also fit the full model with sos to get the partial coefficient
full_fit <- lm(actual_wins ~ preseason_strength + sos, data = d)
sos_coef <- coef(full_fit)[["sos"]]
sos_se   <- summary(full_fit)$coefficients["sos", "Std. Error"]
sos_p    <- summary(full_fit)$coefficients["sos", "Pr(>|t|)"]
r_raw    <- cor(d$sos, d$actual_wins)

# Decile buckets for tail comparison
d$decile <- cut(d$sos_pct, breaks = seq(0, 100, by = 10), labels = 1:10, include.lowest = TRUE)
decile_sum <- d |>
  dplyr::group_by(decile) |>
  dplyr::summarise(
    n = dplyr::n(),
    avg_sos = mean(sos),
    avg_wins = mean(actual_wins),
    avg_residual = mean(wins_residual),
    .groups = "drop"
  )

# ── Panel A: raw scatter, SoS pct vs actual wins ──
p1 <- ggplot(d, aes(x = sos_pct, y = actual_wins)) +
  geom_point(alpha = 0.32, size = 1.6, colour = PAL$slate) +
  geom_smooth(method = "lm", se = TRUE, colour = PAL$accent, fill = PAL$accent,
              linewidth = 1.1, alpha = 0.15, formula = y ~ x) +
  scale_x_continuous(breaks = c(0, 25, 50, 75, 100),
                     labels = c("easiest", "25", "50", "75", "hardest")) +
  scale_y_continuous(breaks = seq(0, 17, by = 4), limits = c(-0.5, 17.5)) +
  labs(
    title    = "Raw correlation",
    subtitle = sprintf("SoS percentile vs actual season wins<br><b style='color:%s'>r = %+.2f</b> — harder schedules win <em>slightly more</em>", PAL$accent, r_raw),
    x = "Season SoS percentile",
    y = "Actual wins"
  ) +
  theme_sched(13)

# ── Panel B: after controlling for own strength ──
p2 <- ggplot(d, aes(x = sos_pct, y = wins_residual)) +
  geom_hline(yintercept = 0, colour = PAL$muted, linewidth = 0.4) +
  geom_point(alpha = 0.32, size = 1.6, colour = PAL$slate) +
  geom_smooth(method = "lm", se = TRUE, colour = PAL$pos, fill = PAL$pos,
              linewidth = 1.1, alpha = 0.15, formula = y ~ x) +
  scale_x_continuous(breaks = c(0, 25, 50, 75, 100),
                     labels = c("easiest", "25", "50", "75", "hardest")) +
  scale_y_continuous(breaks = seq(-6, 6, by = 2), limits = c(-7, 7)) +
  labs(
    title    = "After controlling for own team strength",
    subtitle = sprintf("Residual wins after preseason-strength regression<br><b style='color:%s'>SoS coef = %+.2f wins per 1pt</b> (p = %.2f) — essentially noise", PAL$pos, sos_coef, sos_p),
    x = "Season SoS percentile",
    y = "Wins above own-strength prediction"
  ) +
  theme_sched(13)

# ── Panel C: decile bars, residuals ──
p3 <- ggplot(decile_sum, aes(x = decile, y = avg_residual)) +
  geom_col(fill = ifelse(decile_sum$avg_residual >= 0, PAL$pos, PAL$neg),
           width = 0.78) +
  geom_hline(yintercept = 0, colour = PAL$muted, linewidth = 0.4) +
  geom_text(aes(label = sprintf("%+.2f", avg_residual),
                vjust = ifelse(avg_residual >= 0, -0.5, 1.4)),
            size = 3.4, fontface = "bold", colour = PAL$text) +
  scale_x_discrete(labels = c("1\neasy", "2", "3", "4", "5", "6", "7", "8", "9", "10\nhard")) +
  scale_y_continuous(limits = c(-1.1, 1.1), breaks = c(-1, -0.5, 0, 0.5, 1)) +
  labs(
    title = "Tail effect by SoS decile",
    subtitle = sprintf("Residual wins (above own-strength prediction). Hardest schedules edge +%.2f wins, easiest %+.2f. Even the tails are small.",
                       max(decile_sum$avg_residual), min(decile_sum$avg_residual)),
    x = "Season SoS decile (1 = easiest, 10 = hardest)",
    y = "Avg residual wins"
  ) +
  theme_sched(13)

p <- (p1 | p2) / p3 +
  plot_layout(heights = c(1, 0.85)) +
  plot_annotation(
    title    = "Does Schedule Strength actually matter?",
    subtitle = sprintf(
      "Historical retrospective 2017–2024 (n = %d team-seasons). SoS = avg preseason strength of the team's opponents, percentile-ranked within season.",
      nrow(d)
    ),
    caption  = "Data: nflverse games.csv · preseason strength proxied by avg Vegas spread weeks 1–3 (lower-noise window before mid-season correction).",
    theme = theme(
      plot.title    = element_textbox_simple(size = 22, face = "bold",
                          colour = PAL$ink, margin = margin(b = 6), lineheight = 1.1),
      plot.subtitle = element_textbox_simple(size = 13, colour = PAL$muted,
                          margin = margin(b = 16), lineheight = 1.35),
      plot.caption  = element_text(size = 9, colour = PAL$muted, hjust = 0,
                          margin = margin(t = 10)),
      plot.background = element_rect(fill = PAL$bg, colour = NA),
      plot.margin = margin(18, 24, 14, 24)
    )
  )

save_chart(p, file.path(PROJ_ROOT, "output/sos_matters/chart.png"),
           width = 16, height = 14)
