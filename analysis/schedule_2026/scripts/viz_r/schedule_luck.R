## Schedule luck — horizontal bar of (actual_sos - sim_mean), team logos on y.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/schedule_luck/data.parquet"))

ordinal <- function(n) {
  n <- as.integer(round(n))
  suf <- ifelse(n %% 100 %in% 11:13, "th",
         ifelse(n %% 10 == 1, "st",
         ifelse(n %% 10 == 2, "nd",
         ifelse(n %% 10 == 3, "rd", "th"))))
  paste0(n, suf)
}

d <- d |>
  dplyr::mutate(
    luck_delta = actual_sos - sim_mean,                  # +ve = unlucky (harder)
    sign       = ifelse(luck_delta >= 0, "unlucky", "lucky")
  ) |>
  dplyr::arrange(luck_delta) |>
  dplyr::mutate(team = factor(team, levels = team))

p <- ggplot(d, aes(x = luck_delta, y = team, fill = sign)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%s pct", ordinal(percentile)),
                hjust = ifelse(luck_delta >= 0, -0.15, 1.15)),
            size = 3.4, colour = PAL$text) +
  scale_fill_manual(values = c(lucky = PAL$pos, unlucky = PAL$neg), guide = "none") +
  scale_x_continuous(
    breaks = scales::pretty_breaks(7),
    expand = expansion(mult = c(0.18, 0.18))
  ) +
  geom_vline(xintercept = 0, colour = PAL$muted, linewidth = 0.4) +
  labs(
    title    = "Schedule luck: actual SoS minus randomized-schedule SoS",
    subtitle = paste0(
      "For each team, hold their 6 division games fixed (NFL rule) and randomly redraw the other 11 non-division opponents 10,000 times. ",
      "Compare actual SoS to that simulated distribution. ",
      "<b style='color:#a23b3b'>Positive (red)</b> = actual SoS harder than most random draws (unlucky); ",
      "<b style='color:#1f6f43'>Negative (green)</b> = easier (lucky). ",
      "Percentile label = where the team's actual SoS lands in the simulated distribution."
    ),
    x        = "Actual SoS  −  simulated mean SoS  (sum of opp Vegas wins)",
    y        = NULL,
    caption  = "Data: Monte Carlo over within-conference schedule slots · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/schedule_luck/chart.png"),
           width = 14, height = 12)
