## Defensive quality composite — horizontal bar with component breakdown labels.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/defensive_quality/data.parquet"))

d <- d |>
  dplyr::arrange(def_quality) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$def_quality)
n_rows <- length(levels(d$team))

p <- ggplot(d, aes(x = def_quality, y = team, fill = def_quality)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%.0f  ·  FPA %.0f · cap %.0f · FPI %.0f · WT %.0f",
                                def_quality, fpa_pct, cap_pct, fpi_pct, wt_pct)),
            hjust = -0.05, size = 3.3, colour = PAL$text) +
  scale_fill_gradient(
    low = "#cbd5e1", high = "#1f6f43",
    guide = "none"
  ) +
  scale_x_continuous(
    breaks = scales::pretty_breaks(6),
    limits = c(0, 110),
    expand = expansion(0)
  ) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg, y = n_rows + 0.8,
           label = sprintf("league avg (%.0f)", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "2026 Defensive Quality Composite",
    subtitle = paste0(
      "Four signals percentile-ranked within the league and blended: ",
      "<b>FPA</b> (3-yr weighted PPR fantasy points allowed, recency 50/30/20) <b>· 35%</b>  &nbsp; ",
      "<b>cap spend on defense</b> (Over the Cap 2026) <b>· 25%</b>  &nbsp; ",
      "<b>ESPN FPI defensive efficiency</b> <b>· 25%</b>  &nbsp; ",
      "<b>Vegas win total</b> (overall team strength proxy) <b>· 15%</b>. Higher score = stronger defense to play against."
    ),
    x        = "Composite defensive quality (0-100, higher = better defense)",
    y        = NULL,
    caption  = "Sources: nflverse PBP 2023-25 · OverTheCap.com · ESPN FPI · DraftKings 2026 win totals · logos: nflplotR"
  ) +
  theme_sched(14) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/defensive_quality/chart.png"),
           width = 16, height = 14)
