## CB units chart — horizontal bar of team unit_score (0-100).

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/cb_wr_matchup/data.parquet"))

d <- d |>
  dplyr::arrange(unit_score) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$unit_score)

n_rows <- length(levels(d$team))

p <- ggplot(d, aes(x = unit_score, y = team, fill = unit_score)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%.1f  ·  %s / %s / %s",
                                unit_score,
                                stringr::str_trunc(cb1_name, 14),
                                stringr::str_trunc(cb2_name, 14),
                                stringr::str_trunc(nickel_name, 14))),
            hjust = -0.04, size = 3.4, colour = PAL$text) +
  scale_fill_gradient(
    low = "#cbd5e1", high = "#1f6f43",
    limits = c(0, 100),
    guide = "none"
  ) +
  scale_x_continuous(breaks = seq(20, 100, by = 20),
                     expand = expansion(mult = c(0, 0.4))) +
  geom_vline(xintercept = 50, linetype = "31",
             colour = PAL$muted, linewidth = 0.4) +
  annotate("text", x = 50, y = n_rows + 0.8,
           label = "population median (50)",
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(xlim = c(20, 100), clip = "off") +
  labs(
    title    = "2026 team CB unit strength: PFR coverage composite",
    subtitle = paste0(
      "Unit = <b>0.45·CB1 + 0.35·CB2 + 0.20·Nickel</b>.  ",
      "Per-CB score = 80% PFR adv-def percentile (passer rating + completion % + INT/PD rate, recency-weighted ",
      "2025=0.6, 2024=0.4) + 20% PBP counting stats. ",
      "Unmatched / rookie CBs default to 50 (median)."
    ),
    x        = "CB unit score (population percentile)",
    y        = NULL,
    caption  = "Data: nflreadr load_pfr_advstats(def) + PBP · depth charts via Ourlads · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/cb_wr_matchup/chart.png"),
           width = 14, height = 14)
