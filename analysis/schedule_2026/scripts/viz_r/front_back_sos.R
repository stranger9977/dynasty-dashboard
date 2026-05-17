## Front- vs back-half SoS — scatter with team logos at (h1, h2).

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/front_back_sos/data.parquet"))

xmid <- mean(c(min(d$h1_avg), max(d$h1_avg)))
ymid <- mean(c(min(d$h2_avg), max(d$h2_avg)))

# Pad axes equally so the y=x reference line spans the visible area.
lo <- min(c(d$h1_avg, d$h2_avg)) - 0.3
hi <- max(c(d$h1_avg, d$h2_avg)) + 0.3

mid_diag <- mean(c(lo, hi))

# Quadrant descriptors (no trade-jargon — just the schedule shape)
inset <- 0.45
quad_labels <- data.frame(
  x = c(lo + inset, hi - inset, lo + inset, hi - inset),
  y = c(hi - inset, hi - inset, lo + inset, lo + inset),
  hjust = c(0, 1, 0, 1),
  vjust = c(1, 1, 0, 0),
  label = c(
    "Easy start → hard finish",
    "Hard schedule all year",
    "Easy schedule all year",
    "Hard start → easy finish"
  )
)

p <- ggplot(d, aes(x = h1_avg, y = h2_avg)) +
  geom_abline(slope = 1, intercept = 0,
              colour = PAL$muted, linetype = "31", linewidth = 0.5) +
  geom_text(
    data = quad_labels,
    aes(x = x, y = y, label = label, hjust = hjust, vjust = vjust),
    colour = PAL$muted, size = 4.0, fontface = "italic",
    lineheight = 1.0, inherit.aes = FALSE
  ) +
  nflplotR::geom_nfl_logos(aes(team_abbr = team), width = 0.052, alpha = 0.95) +
  annotate("text", x = mid_diag + 0.1, y = mid_diag - 0.18,
           label = "diagonal = same difficulty in both halves",
           colour = PAL$muted, size = 3.4, hjust = 0, angle = 45) +
  scale_x_continuous(limits = c(lo, hi), breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = 0.02)) +
  scale_y_continuous(limits = c(lo, hi), breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = 0.02)) +
  labs(
    title    = "First-half vs second-half schedule difficulty (Weeks 1–9 vs 10–18)",
    subtitle = "Average opponent Vegas win total in each half of the season. Above the diagonal = harder second half. Below = easier second half.",
    x        = "First half (Weeks 1–9) avg opponent win total",
    y        = "Second half (Weeks 10–18) avg opponent win total",
    caption  = "Data: DraftKings 2026 win totals · logos: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    panel.grid.major.x = element_blank(),
    panel.grid.major.y = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/front_back_sos/chart.png"),
           width = 12, height = 10)
