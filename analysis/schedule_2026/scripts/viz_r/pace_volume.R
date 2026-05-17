## Pace / volume — horizontal bar of projected_2026_total_plays.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/pace_volume/data.parquet"))

d <- d |>
  dplyr::arrange(projected_2026_total_plays) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$projected_2026_total_plays)

n_rows <- length(levels(d$team))

xlim_lo <- floor(min(d$projected_2026_total_plays) / 10) * 10
xlim_hi <- ceiling(max(d$projected_2026_total_plays) / 10) * 10

p <- ggplot(d, aes(x = projected_2026_total_plays, y = team,
                   fill = projected_2026_total_plays)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%s plays (%.1f / %.1f)",
                                scales::comma(round(projected_2026_total_plays)),
                                off_plays_per_game, def_plays_allowed_per_game)),
            hjust = -0.04, size = 3.4, colour = PAL$text) +
  scale_fill_gradient(
    low = "#cbd5e1", high = "#274690",
    guide = "none"
  ) +
  scale_x_continuous(labels = scales::comma_format(),
                     breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = c(0, 0.05))) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg, y = n_rows + 0.8,
           label = sprintf("league avg %s plays", scales::comma(round(league_avg))),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(xlim = c(xlim_lo, xlim_hi), clip = "off") +
  labs(
    title    = "Projected 2026 offensive plays: own pace × opponent pace allowed",
    subtitle = paste0(
      "Combines a team's own 2025 offensive plays/game with each opponent's defensive plays-allowed/game, ",
      "summed across 17 games."
    ),
    x        = "Projected total offensive plays (regular season)",
    y        = NULL,
    caption  = "Data: 2025 PBP via nflverse + 2026 schedule · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/pace_volume/chart.png"),
           width = 14, height = 14)
