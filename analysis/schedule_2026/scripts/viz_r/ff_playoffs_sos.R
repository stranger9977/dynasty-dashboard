## FF playoffs SoS — Weeks 14-16 only, RB/WR/TE heatmap. Annotate playoff_games_count.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/ff_playoffs_sos/data.parquet"))

long <- d |>
  dplyr::select(team, rb_sos_score, wr_sos_score, te_sos_score, playoff_games_count) |>
  tidyr::pivot_longer(c(rb_sos_score, wr_sos_score, te_sos_score),
                      names_to = "pos", values_to = "score") |>
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

# Per-team playoff games count label — flag teams with !=3 games (W14-16 bye)
pg <- d |>
  dplyr::transmute(team = factor(team, levels = ord), pg = playoff_games_count) |>
  dplyr::filter(pg != 3)

p <- ggplot(long, aes(x = pos, y = team, fill = score)) +
  geom_tile(colour = "white", linewidth = 0.7) +
  geom_text(aes(label = sprintf("%.0f", score),
                colour = ifelse(score > 60 | score < 40, "white", "black")),
            size = 4.0, fontface = "bold") +
  scale_colour_identity() +
  geom_text(
    data = pg,
    aes(x = 0.4, y = team, label = sprintf("⚠ %d gms", pg)),
    colour = PAL$neg, size = 3.2, fontface = "bold",
    inherit.aes = FALSE
  ) +
  scale_fill_distiller(
    palette = "RdBu", direction = -1,
    limits = c(0, 100), values = scales::rescale(c(0, 50, 100)),
    name = "FF-playoffs SoS percentile (Weeks 14–16)",
    guide = guide_colourbar(barwidth = 18, barheight = 0.55,
                            title.position = "top", title.hjust = 0.5)
  ) +
  scale_x_discrete(position = "top", expand = expansion(mult = c(0.10, 0))) +
  scale_y_discrete(expand = expansion(0)) +
  labs(
    title    = "Fantasy-playoffs SoS for RB / WR / TE (Weeks 14–16)",
    subtitle = paste0(
      "Cells are percentiles (0 = easiest schedule for that position, 100 = hardest). ",
      "Teams sorted by average position SoS over fantasy playoff weeks. ",
      "<b style='color:#a23b3b'>⚠ flags teams with a W14 bye — only 2 playoff games</b>."
    ),
    x        = NULL,
    y        = NULL,
    caption  = "Data: 2025 PBP opponent FPA · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.text.x         = element_text(size = 14, face = "bold"),
    axis.ticks          = element_blank(),
    panel.grid          = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/ff_playoffs_sos/chart.png"),
           width = 9, height = 13)
