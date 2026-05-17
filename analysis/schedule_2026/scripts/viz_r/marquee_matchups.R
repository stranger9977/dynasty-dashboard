## Marquee WR-vs-CB matchups — top 18 games where elite WR meets elite CB unit.
## Designed to look like a "matchup card": WR headshot + opposing team logo + week.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

d <- read_parquet(file.path(PROJ_ROOT, "output/cb_wr_matchup/marquee_matchups.parquet"))

# Resolve WR gsis_ids for headshots
gsis <- resolve_gsis(d$name, position = "WR", team = d$team)
d$gsis_id  <- gsis$gsis_id

# Stable ordering: highest marquee score at top
d <- d |>
  dplyr::arrange(marquee_score) |>
  dplyr::mutate(row_id = factor(seq_len(dplyr::n())),
                pair_label = sprintf("Wk %d · %s (%s) vs %s",
                                     as.integer(week), name, team, opp),
                detail_label = sprintf("WR %.0f × CB %.0f", blended_value, cb_unit))

x_max <- max(d$marquee_score) * 1.40
headshot_x <- max(d$marquee_score) * 0.08

p <- ggplot(d, aes(y = row_id)) +
  # the bar
  geom_col(aes(x = marquee_score, fill = marquee_score),
           width = 0.72, colour = NA) +
  # WR headshot at left interior of bar
  nflplotR::geom_nfl_headshots(
    aes(player_gsis = gsis_id),
    x = headshot_x,
    height = 0.055, na.rm = TRUE
  ) +
  # opposing team logo at end of bar
  nflplotR::geom_nfl_logos(
    aes(team_abbr = opp, x = marquee_score),
    width = 0.034, alpha = 1
  ) +
  # Week + WR + matchup label right of logo (one line, bigger text)
  geom_text(aes(label = pair_label, x = marquee_score),
            hjust = -0.35, size = 3.6, fontface = "bold",
            colour = PAL$text, nudge_y = 0.18) +
  geom_text(aes(label = detail_label, x = marquee_score),
            hjust = -0.35, size = 3.0,
            colour = PAL$muted, nudge_y = -0.22) +
  scale_fill_gradient(
    low = "#7a9ec7", high = "#1a3a6b",
    guide = "none"
  ) +
  scale_x_continuous(limits = c(min(d$marquee_score) - 8, x_max),
                     breaks = scales::pretty_breaks(6),
                     expand = expansion(0),
                     oob = scales::oob_keep) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "2026 marquee WR-vs-CB matchups: top 18 games",
    subtitle = paste0(
      "For the top 40 WRs by blended dynasty value, every game scored as ",
      "<b>WR quality × opponent CB unit / 100</b>. Deduped to one entry per (WR, opponent) ",
      "and ranked. These are the films-festival matchups — and the toughest weeks to start that WR."
    ),
    x        = "Marquee score (0-100 scale)",
    y        = NULL,
    caption  = "WR ratings: blended FC/KTC/LR · CB ratings: PFR adv-def via nflreadr · logos & headshots: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = element_blank(),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/cb_wr_matchup/marquee_matchups.png"),
           width = 16, height = 14)
