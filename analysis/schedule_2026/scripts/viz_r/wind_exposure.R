## Wind exposure — horizontal bar of total wind exposure (mph-games), team logos on y.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/wind_exposure/data.parquet"))

d <- d |>
  dplyr::arrange(total_wind_exposure_mph_games) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$total_wind_exposure_mph_games)

p <- ggplot(d, aes(x = total_wind_exposure_mph_games, y = team,
                   fill = total_wind_exposure_mph_games)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%.0f mph-games  (%d high-wind)",
                                total_wind_exposure_mph_games,
                                high_wind_games_count)),
            hjust = -0.1, size = 3.4, colour = PAL$text) +
  scale_fill_gradient(
    low = "#e2e8f0", high = "#1e293b",
    guide = "none"
  ) +
  scale_x_continuous(breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = c(0, 0.32))) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg, y = length(levels(d$team)) + 0.8,
           label = sprintf("league avg %.0f", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "Wind exposure: sum of (wind mph × games) at outdoor venues",
    subtitle = "Higher = more games in windy outdoor stadiums. Annotations show high-wind games (15+ mph) & late-season outdoor games (Wk 14+).",
    x        = "Wind exposure (mph-games)",
    y        = NULL,
    caption  = "Data: Open-Meteo historical wind climatology by stadium · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/wind_exposure/chart.png"),
           width = 14, height = 14)
