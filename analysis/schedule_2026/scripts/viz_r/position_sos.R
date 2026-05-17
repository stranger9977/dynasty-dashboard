## Position SoS — 32x3 heatmap (RB/WR/TE) with team logos on y, diverging palette around 50.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/position_sos/data.parquet"))

long <- d |>
  dplyr::select(team, rb_sos_score, wr_sos_score, te_sos_score) |>
  tidyr::pivot_longer(-team, names_to = "pos", values_to = "score") |>
  dplyr::mutate(
    pos = factor(pos,
                 levels = c("rb_sos_score", "wr_sos_score", "te_sos_score"),
                 labels = c("RB", "WR", "TE"))
  )

# order teams by mean across the three positions (highest = hardest schedule for skill)
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
    name = "Position SoS percentile (0 = easiest, 100 = hardest)",
    guide = guide_colourbar(barwidth = 18, barheight = 0.55,
                            title.position = "top", title.hjust = 0.5)
  ) +
  scale_x_discrete(position = "top", expand = expansion(0)) +
  scale_y_discrete(expand = expansion(0)) +
  labs(
    title    = "Position-level SoS for RB / WR / TE (full season)",
    subtitle = "Cells are percentiles (0 = easiest schedule for that position, 100 = hardest). Teams sorted by avg SoS across the three.",
    x        = NULL,
    y        = NULL,
    caption  = "Data: 2025 PBP opponent FPA × 2026 schedule · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.text.x         = element_text(size = 14, face = "bold"),
    axis.ticks          = element_blank(),
    panel.grid          = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/position_sos/chart.png"),
           width = 9, height = 13)
