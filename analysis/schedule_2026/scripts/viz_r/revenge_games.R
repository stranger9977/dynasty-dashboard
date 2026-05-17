## Revenge games — per-week stacked bar by position. Headshots for top names in busiest weeks.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/revenge_games/data.parquet"))

d <- d |>
  dplyr::mutate(
    position = factor(position, levels = c("QB", "RB", "WR", "TE", "K", "DEF"))
  )

agg <- d |>
  dplyr::filter(!is.na(position)) |>
  dplyr::count(revenge_week, position, name = "n")

# Headshots: spotlight the most-experienced (highest years_exp) player from each of the
# top 3 weeks (only show one or two per week to keep the chart breathable).
weekly_total <- d |> dplyr::count(revenge_week, name = "total")
# Pick the 4 busiest weeks that are at least 2 apart, greedy by total desc.
ranked <- weekly_total |> dplyr::arrange(desc(total))
top_weeks <- integer(0)
for (w in ranked$revenge_week) {
  if (all(abs(top_weeks - w) >= 2)) top_weeks <- c(top_weeks, w)
  if (length(top_weeks) == 4) break
}
top_weeks <- sort(top_weeks)

spotlight <- d |>
  dplyr::filter(revenge_week %in% top_weeks, position %in% c("QB", "RB", "WR", "TE")) |>
  dplyr::group_by(revenge_week) |>
  dplyr::arrange(desc(years_exp)) |>
  dplyr::slice_head(n = 1) |>
  dplyr::ungroup()

# Resolve gsis_id
gsis <- resolve_gsis(spotlight$player_name, spotlight$position, spotlight$current_team)
spotlight$gsis_id      <- gsis$gsis_id
spotlight$matched      <- gsis$matched

# Position-stacked palette
pos_pal <- c(
  "QB"  = "#274690",
  "RB"  = "#1f6f43",
  "WR"  = "#d97706",
  "TE"  = "#7a3b9b",
  "K"   = "#94a3b8",
  "DEF" = "#a23b3b"
)

y_max_chart <- max(weekly_total$total) + 9
y_top_zone  <- y_max_chart - 3

p <- ggplot(agg, aes(x = revenge_week, y = n, fill = position)) +
  geom_col(width = 0.85, colour = "white", linewidth = 0.4) +
  geom_text(
    data = weekly_total,
    aes(x = revenge_week, y = total, label = total),
    vjust = -0.6, size = 3.3, colour = PAL$text, inherit.aes = FALSE
  ) +
  # Spotlight: name label ABOVE headshot, then headshot — prevents overlap with column totals
  geom_text(
    data = spotlight,
    aes(x = revenge_week, y = y_top_zone + 1.2,
        label = sprintf("%s\n%s ← %s", player_name, current_team, former_team)),
    size = 3.0, colour = PAL$text, lineheight = 0.95,
    inherit.aes = FALSE, fontface = "bold"
  ) +
  nflplotR::geom_nfl_headshots(
    data = spotlight |> dplyr::filter(matched),
    aes(player_gsis = gsis_id, x = revenge_week, y = y_top_zone - 2),
    width = 0.06,
    inherit.aes = FALSE
  ) +
  scale_fill_manual(values = pos_pal, name = "Position",
                    guide = guide_legend(nrow = 1)) +
  scale_x_continuous(breaks = sort(unique(agg$revenge_week)), expand = expansion(0.02)) +
  scale_y_continuous(limits = c(0, y_max_chart), expand = expansion(0),
                     breaks = scales::pretty_breaks(6)) +
  labs(
    title    = "Revenge games on the 2026 schedule by week",
    subtitle = paste0(
      "Each bar counts skill-position players facing a former team. ",
      "Spotlight headshots = the most-experienced names in the league's four busiest revenge weeks."
    ),
    x        = "Week",
    y        = "Revenge-game count",
    caption  = "Data: 2025 → 2026 team changes for skill positions · headshots: nflplotR/nflreadr"
  ) +
  theme_sched(13) +
  theme(
    axis.text.x = element_text(size = 11),
    panel.grid.major.x = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/revenge_games/chart.png"),
           width = 14, height = 9)
