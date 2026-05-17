## Bye-leverage — segmented bars by bye_classification, team logos on y, week label.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/bye_leverage/data.parquet"))

# Order: most positive rest_differential at top
d <- d |>
  dplyr::arrange(rest_differential_sum, bye_week) |>
  dplyr::mutate(
    team = factor(team, levels = team),
    bye_classification = factor(bye_classification,
                                levels = c("Early", "FF-optimal", "Mid", "Late", "FF-risky"))
  )

cls_palette <- c(
  "Early"      = "#1d4ed8",
  "FF-optimal" = "#1f6f43",
  "Mid"        = "#94a3b8",
  "Late"       = "#d97706",
  "FF-risky"   = "#a23b3b"
)

p <- ggplot(d, aes(x = rest_differential_sum, y = team, fill = bye_classification)) +
  geom_col(width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("Wk %d · %+d rest · %d off-bye opps",
                                bye_week, rest_differential_sum, opps_off_bye),
                hjust = ifelse(rest_differential_sum >= 0, -0.1, 1.1)),
            size = 3.4, colour = PAL$text) +
  scale_fill_manual(values = cls_palette, name = "Bye-week classification",
                    drop = FALSE,
                    guide = guide_legend(nrow = 1, title.position = "left")) +
  scale_x_continuous(
    breaks = scales::pretty_breaks(7),
    expand = expansion(mult = c(0.45, 0.45))
  ) +
  geom_vline(xintercept = 0, colour = PAL$muted, linewidth = 0.4) +
  labs(
    title    = "Bye-week leverage: rest-day differential & opponents coming off their bye",
    subtitle = paste0(
      "For each of the team's 17 games, compute (own days of rest − opponent days of rest) and sum across the season. ",
      "Positive bar = team had more rest than opponents on net; negative = rest deficit. ",
      "Bar color = bye-week timing classification. ",
      "Inline label shows the team's bye week and how many of their opponents come off a bye (rested opponent = disadvantage)."
    ),
    x        = "Season rest-day differential (sum of own minus opp rest days)",
    y        = NULL,
    caption  = "Data: 2026 schedule · logos: nflplotR"
  ) +
  theme_sched(14) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/bye_leverage/chart.png"),
           width = 16, height = 13)
