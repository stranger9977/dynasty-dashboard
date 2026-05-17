## Game-script RB — horizontal bar of total_leading_share, annotated with positive-script games.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/game_script_rb/data.parquet"))

d <- d |>
  dplyr::arrange(total_leading_share) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$total_leading_share)

n_rows <- length(levels(d$team))

p <- ggplot(d, aes(x = total_leading_share, y = team, fill = total_leading_share)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%.1f · %d+ scripts", total_leading_share,
                                positive_script_games_count)),
            hjust = -0.1, size = 3.4, colour = PAL$text) +
  scale_fill_gradient(
    low = "#cbd5e1", high = "#1f6f43",
    guide = "none"
  ) +
  scale_x_continuous(breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = c(0, 0.05))) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg, y = n_rows + 0.8,
           label = sprintf("league avg %.1f", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(xlim = c(7.2, 9.4), clip = "off") +
  labs(
    title    = "Game-script for RBs: expected leading-game share by team",
    subtitle = paste0(
      "Sum of P(team leads in 2nd half) across 17 games, ",
      "derived from Vegas implied spreads. ",
      "Higher = more rushing volume late, more positive script for RBs."
    ),
    x        = "Expected leading-game share (out of 17)",
    y        = NULL,
    caption  = "Data: DraftKings 2026 spreads · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/game_script_rb/chart.png"),
           width = 14, height = 13)
