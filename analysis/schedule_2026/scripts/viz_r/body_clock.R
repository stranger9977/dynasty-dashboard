## Body clock — diverging horizontal bar of net_body_clock (advantage_games - disadvantage_games).

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/body_clock/data.parquet"))

# Use disadvantage_games as the primary metric (sequential, all positive).
# Higher = more body-clock pain — easier to read than the noisy net metric.
d <- d |>
  dplyr::arrange(disadvantage_games) |>
  dplyr::mutate(team = factor(team, levels = team))

p <- ggplot(d, aes(x = disadvantage_games, y = team, fill = disadvantage_games)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(
    aes(label = sprintf("%d disadv · %d adv", disadvantage_games, advantage_games),
        hjust = -0.1),
    size = 3.4, colour = PAL$text
  ) +
  scale_fill_gradient(
    low = "#cbd5e1", high = PAL$neg,
    guide = "none"
  ) +
  scale_x_continuous(
    breaks = scales::pretty_breaks(7),
    expand = expansion(mult = c(0, 0.30))
  ) +
  labs(
    title    = "Body-clock burden: kickoff-time effects across the 2026 schedule",
    subtitle = paste0(
      "Advantage = team plays at home body-clock hour while opp is off-cycle. ",
      "Disadvantage = reverse. West-coast teams cluster at the top."
    ),
    x        = "Disadvantage games",
    y        = NULL,
    caption  = "Data: 2026 schedule kickoff times & team time zones · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/body_clock/chart.png"),
           width = 14, height = 14)
