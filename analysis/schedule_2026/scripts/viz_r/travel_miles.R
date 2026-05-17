## Travel miles — stacked horizontal bar: domestic + international + a longest-trip marker.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/travel_miles/data.parquet"))

d <- d |>
  dplyr::arrange(total_miles) |>
  dplyr::mutate(
    team        = factor(team, levels = team),
    domestic    = total_miles - intl_miles,
    intl       = intl_miles
  )

long <- d |>
  dplyr::select(team, domestic, intl) |>
  tidyr::pivot_longer(c(domestic, intl), names_to = "kind", values_to = "miles") |>
  dplyr::mutate(kind = factor(kind, levels = c("domestic", "intl")))

league_avg <- mean(d$total_miles)

p <- ggplot(long, aes(x = miles, y = team, fill = kind)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(data = d, inherit.aes = FALSE,
            aes(x = total_miles, y = team,
                label = sprintf("%s mi", scales::comma(round(total_miles)))),
            hjust = -0.12, size = 3.1, colour = PAL$text) +
  scale_fill_manual(
    values = c(domestic = "#3b6aa8", intl = "#d97706"),
    guide = "none"
  ) +
  scale_x_continuous(labels = scales::comma_format(),
                     breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = c(0, 0.12))) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.5) +
  annotate("text", x = league_avg, y = length(levels(d$team)) + 0.8,
           label = sprintf("league avg %s mi", scales::comma(round(league_avg))),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "2026 travel burden: total flight miles",
    subtitle = "<span style='color:#3b6aa8'><b>Domestic miles</b></span> + <span style='color:#d97706'><b>international miles</b></span> (London, Berlin, Madrid, São Paulo, Rio, Melbourne). Visiting clubs pay the overseas tax.",
    x        = "Total miles flown (regular season)",
    y        = NULL,
    caption  = "Data: 2026 schedule + stadium coordinates · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/travel_miles/chart.png"),
           width = 14, height = 14)
