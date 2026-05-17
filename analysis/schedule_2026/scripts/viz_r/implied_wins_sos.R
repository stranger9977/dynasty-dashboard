## Implied wins SOS — horizontal bar, team logos on y, diverging by sos_vs_league_avg.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/implied_wins_sos/data.parquet"))

d <- d |>
  dplyr::arrange(total_opp_implied_wins) |>
  dplyr::mutate(
    team = factor(team, levels = team),
    sign = ifelse(sos_vs_league_avg >= 0, "harder", "easier")
  )

league_avg <- mean(d$total_opp_implied_wins, na.rm = TRUE)

xmax <- max(d$total_opp_implied_wins) * 1.05
xmin <- 130

# We display "above 130" baseline so differences are readable.
d2 <- d |>
  dplyr::mutate(bar_x = total_opp_implied_wins - xmin)

p <- ggplot(d2, aes(x = bar_x, y = team, fill = sos_vs_league_avg)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%+.2f", sos_vs_league_avg)),
            hjust = -0.18, size = 3.4, colour = PAL$text) +
  scale_fill_gradient2(
    low = PAL$diverge_lo, mid = "#d8dde6", high = PAL$diverge_hi,
    midpoint = 0,
    limits = c(-max(abs(d$sos_vs_league_avg)), max(abs(d$sos_vs_league_avg))),
    guide = "none"
  ) +
  scale_x_continuous(
    breaks = function(lim) (scales::pretty_breaks(6)(lim + xmin)) - xmin,
    labels = function(b) sprintf("%g", b + xmin),
    expand = expansion(mult = c(0, 0.08))
  ) +
  geom_vline(xintercept = league_avg - xmin, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg - xmin, y = length(levels(d2$team)) + 0.8,
           label = sprintf("league avg %.1f", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.5) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "2026 schedule difficulty by Vegas implied opponent wins",
    subtitle = sprintf("Total of every opponent's 2026 win total.  League average = <b>%.1f</b>.  Bar color shows whether the schedule is above or below average; bar length shows by how much.",
                       league_avg),
    x        = "Total opponent implied wins (sum of opp Vegas win totals)",
    y        = NULL,
    caption  = "Data: DraftKings 2026 win totals via nflverse · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y = element_blank(),
    panel.grid.major.y = element_blank(),
    plot.margin = margin(20, 28, 14, 20)
  )

save_chart(p, file.path(PROJ_ROOT, "output/implied_wins_sos/chart.png"),
           width = 14, height = 13)
