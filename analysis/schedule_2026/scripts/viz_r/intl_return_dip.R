## International return-dip — historical effect size + 2026 affected games.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")
library(patchwork)
library(stringr)

hist <- read_parquet(file.path(PROJ_ROOT,
                               "output/intl_return_dip/historical_return_games.parquet"))
present <- read_parquet(file.path(PROJ_ROOT, "output/intl_return_dip/data.parquet"))

# ---- Left panel: density of return-game margins, with mean line. ----
# Build baseline: all NFL games' point margins by side. Approx using simple normal
# centered at zero with sd matching margins — but the parquet has return_margin from
# the team's perspective. Show distribution and median.

hist <- hist |> dplyr::filter(!is.na(return_margin))
med <- median(hist$return_margin)
mn  <- mean(hist$return_margin)
n   <- nrow(hist)

cover_rate <- mean(hist$return_covered, na.rm = TRUE)

mn_colour <- if (mn < 0) PAL$neg else PAL$pos
verdict <- if (abs(mn) < 1) "essentially neutral" else
           if (mn < 0) "slight dip" else "slight bounce"

p1 <- ggplot(hist, aes(x = return_margin)) +
  geom_histogram(binwidth = 3, fill = "#cbd5e1", colour = "white", linewidth = 0.4) +
  geom_vline(xintercept = 0, colour = PAL$muted, linewidth = 0.5) +
  geom_vline(xintercept = mn, colour = mn_colour, linewidth = 1.1) +
  annotate("text", x = mn, y = Inf, vjust = 1.6, hjust = -0.05,
           label = sprintf("avg margin %+.2f", mn),
           colour = mn_colour, size = 4.0, fontface = "bold") +
  annotate("text", x = 0, y = Inf, vjust = 3.4, hjust = 1.05,
           label = "tie (0)", colour = PAL$muted, size = 3.4) +
  scale_x_continuous(breaks = scales::pretty_breaks(8)) +
  labs(
    title    = sprintf("Historical return-game margins — %s", verdict),
    subtitle = sprintf(
      "Distribution of point margin (positive = win) in the next game after an int'l trip, 2007–2025.  n = %d.  ATS cover rate %.0f%%.",
      n, 100 * cover_rate
    ),
    x        = "Return-game point margin (team perspective)",
    y        = "Games"
  ) +
  theme_sched(13)

# ---- Right panel: 2026 affected games — a small table-style display. ----
present_disp <- present |>
  dplyr::mutate(
    label = sprintf("%s%s vs %s", int_team,
                    ifelse(int_side == "home", "", "@"),
                    int_opponent),
    return = sprintf("Wk %d %s%s",
                     return_week,
                     ifelse(return_home_away == "home", "vs ", "@ "),
                     return_opponent),
    venue_short = stringr::str_remove(int_venue, " Stadium| Cricket Ground"),
    yidx = dplyr::row_number()
  )

return_colour <- if (mn < 0) PAL$neg else PAL$pos

p2 <- ggplot(present_disp, aes(y = -yidx)) +
  geom_text(aes(x = 0, label = sprintf("Wk %d · %s",
                                       int_game_week, label)),
            hjust = 0, size = 3.7, fontface = "bold",
            colour = PAL$text) +
  geom_text(aes(x = 0.42, label = venue_short),
            hjust = 0, size = 3.2, colour = PAL$muted) +
  geom_text(aes(x = 0.78, label = return),
            hjust = 0, size = 3.6, colour = return_colour,
            fontface = "bold") +
  scale_x_continuous(limits = c(-0.02, 1.1), expand = expansion(0)) +
  scale_y_continuous(expand = expansion(add = c(1, 1.5))) +
  labs(
    title    = "2026 schedule: who returns from an int'l trip",
    subtitle = "Each row: the int'l game (week · matchup · venue) and the team's next-week return game."
  ) +
  theme_void(base_size = 13) +
  theme(
    plot.background     = element_rect(fill = PAL$bg, colour = NA),
    panel.background    = element_rect(fill = PAL$bg, colour = NA),
    plot.title          = element_textbox_simple(
                            size = 19, face = "bold", colour = PAL$ink,
                            margin = margin(b = 6), lineheight = 1.15),
    plot.subtitle       = element_textbox_simple(
                            size = 13, colour = PAL$muted,
                            margin = margin(b = 12), lineheight = 1.3),
    plot.title.position = "plot",
    plot.margin         = margin(18, 22, 14, 18)
  )

p <- (p1 | p2) + plot_layout(widths = c(1.1, 1))

save_chart(p, file.path(PROJ_ROOT, "output/intl_return_dip/chart.png"),
           width = 16, height = 8.5)
