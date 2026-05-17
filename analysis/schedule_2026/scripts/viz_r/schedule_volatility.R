## Schedule volatility — horizontal bar of opp_wt_std (boom/bust schedule).

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/schedule_volatility/data.parquet"))

d <- d |>
  dplyr::arrange(opp_wt_std) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$opp_wt_std)

p <- ggplot(d, aes(x = opp_wt_std, y = team, fill = opp_wt_std)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%.2f", opp_wt_std)),
            hjust = -0.18, size = 3.3, colour = PAL$text) +
  scale_fill_gradient(
    low = PAL$cool, high = PAL$warm,
    name = NULL,
    guide = "none"
  ) +
  scale_x_continuous(breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = c(0, 0.15))) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg, y = length(levels(d$team)) + 0.8,
           label = sprintf("league avg %.2f", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "Schedule volatility: stdev of opponent Vegas win totals",
    subtitle = "Standard deviation of opponent Vegas win totals across the team's 17 games. Low = same-tier opponents every week (steady). High = mix of haves and have-nots (boom-or-bust). Steady schedules → records cluster near projection; boom-bust schedules → wider range of plausible final records.",
    x        = "Stdev of opponent win totals (week-to-week)",
    y        = NULL,
    caption  = "Data: 2026 schedule × DraftKings win totals · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/schedule_volatility/chart.png"),
           width = 14, height = 12)
