## Schedule Leverage Index — composite of 5 non-opponent-quality burdens.
## Horizontal bar of leverage_index (0-100) with each team's top burden labeled.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/schedule_leverage/data.parquet"))

d <- d |>
  dplyr::arrange(leverage_index) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$leverage_index)
n_rows <- length(levels(d$team))

p <- ggplot(d, aes(x = leverage_index, y = team)) +
  geom_col(width = 0.78, colour = NA, fill = PAL$slate) +
  geom_text(aes(label = sprintf("%.0f  ·  driver: %s (%.0f)",
                                leverage_index, top_burden, top_burden_pct),
                hjust = -0.1),
            size = 3.4, colour = PAL$text) +
  scale_x_continuous(limits = c(0, 110),
                     breaks = seq(0, 100, by = 20),
                     expand = expansion(0)) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg, y = n_rows + 0.8,
           label = sprintf("league avg (%.0f)", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "2026 Schedule Leverage Index",
    subtitle = paste0(
      "Composite of 5 non-opponent-quality schedule burdens, each percentile-ranked within the league ",
      "and equal-weighted: <b>rest differential · opponents-off-bye · body-clock disadvantage · travel miles · wind exposure</b>. ",
      "Higher score = tougher schedule environment to navigate, independent of opponent strength."
    ),
    x        = "Leverage index (0-100, higher = more environmental burden)",
    y        = NULL,
    caption  = "Sources: bye_leverage · body_clock · travel_miles · wind_exposure (all 2026 schedule-derived) · logos: nflplotR"
  ) +
  theme_sched(14) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/schedule_leverage/chart.png"),
           width = 16, height = 13)
