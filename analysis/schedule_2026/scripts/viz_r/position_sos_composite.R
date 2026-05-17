## Position SoS — composite-adjusted heatmap.
## 32 teams x 3 positions (RB/WR/TE). Composite blends position-FPA + cap spend + FPI + Vegas WT.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/position_sos_composite/data.parquet"))

long <- d |>
  dplyr::select(team, rb_sos_score, wr_sos_score, te_sos_score) |>
  tidyr::pivot_longer(-team, names_to = "pos", values_to = "score") |>
  dplyr::mutate(
    pos = factor(pos,
                 levels = c("rb_sos_score", "wr_sos_score", "te_sos_score"),
                 labels = c("RB", "WR", "TE"))
  )

ord <- long |>
  dplyr::group_by(team) |>
  dplyr::summarise(m = mean(score)) |>
  dplyr::arrange(m) |>
  dplyr::pull(team)
long$team <- factor(long$team, levels = ord)

p <- ggplot(long, aes(x = pos, y = team, fill = score)) +
  geom_tile(colour = "white", linewidth = 0.7) +
  geom_text(aes(label = sprintf("%.0f", score),
                colour = ifelse(score > 60 | score < 40, "white", "black")),
            size = 4.0, fontface = "bold") +
  scale_colour_identity() +
  scale_fill_distiller(
    palette = "RdBu", direction = -1,
    limits = c(0, 100), values = scales::rescale(c(0, 50, 100)),
    name = "Composite position SoS (0 = easiest, 100 = toughest)",
    guide = guide_colourbar(barwidth = 18, barheight = 0.55,
                            title.position = "top", title.hjust = 0.5)
  ) +
  scale_x_discrete(position = "top", expand = expansion(0)) +
  scale_y_discrete(expand = expansion(0)) +
  labs(
    title    = "Position SoS — composite-adjusted (RB / WR / TE)",
    subtitle = paste0(
      "Each cell is the team's percentile rank of opponents' position-specific defensive quality. ",
      "The composite blends <b>50% position FPA</b> (recency-weighted 50/30/20) with ",
      "<b>20% defensive cap spend</b> · <b>20% ESPN FPI</b> · <b>10% Vegas win total</b>. ",
      "More forward-looking than raw FPA alone."
    ),
    x        = NULL,
    y        = NULL,
    caption  = "Sources: nflverse PBP 2023-25 · OverTheCap.com 2026 cap · ESPN FPI · DraftKings 2026 win totals · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.text.x         = element_text(size = 14, face = "bold"),
    axis.ticks          = element_blank(),
    panel.grid          = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/position_sos_composite/chart.png"),
           width = 10, height = 14)
