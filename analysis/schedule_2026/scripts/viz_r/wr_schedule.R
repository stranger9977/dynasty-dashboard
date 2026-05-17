## WR schedule strength — per team, with WR1 headshot and team logo.
## Bar = avg opponent CB unit score across 17 games.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

wr_sched <- read_parquet(file.path(PROJ_ROOT, "output/cb_wr_matchup/wr_schedules.parquet"))

# Pick the team's top WR using the dynasty dashboard's blended value rankings
merged <- read_parquet("/Users/nick/projects/dynasty-dashboard/data/merged.parquet")
wrs <- merged |>
  dplyr::filter(position == "WR", team != "FA") |>
  dplyr::mutate(team = dplyr::recode(team,
    GBP = "GB", KCC = "KC", LVR = "LV", NOS = "NO",
    SFO = "SF", TBB = "TB", LAR = "LA"
  )) |>
  dplyr::select(name, team, blended_value)

top_wr_per_team <- wrs |>
  dplyr::group_by(team) |>
  dplyr::slice_max(blended_value, n = 1, with_ties = FALSE) |>
  dplyr::ungroup() |>
  dplyr::rename(top_wr = name)

team_summary <- wr_sched |>
  dplyr::distinct(team, avg_opp_cb_score, total_opp_cb_score) |>
  dplyr::left_join(top_wr_per_team, by = "team")

# Resolve gsis_id for each top WR for headshots
gsis <- resolve_gsis(team_summary$top_wr, position = "WR", team = team_summary$team)
team_summary$gsis_id <- gsis$gsis_id
team_summary$matched <- gsis$matched

team_summary <- team_summary |>
  dplyr::arrange(avg_opp_cb_score) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(team_summary$avg_opp_cb_score)
n_rows <- length(levels(team_summary$team))

p <- ggplot(team_summary, aes(y = team, x = avg_opp_cb_score)) +
  geom_col(aes(fill = avg_opp_cb_score), width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%.1f  ·  %s", avg_opp_cb_score, top_wr),
                x = avg_opp_cb_score),
            hjust = -0.1, size = 3.4, colour = PAL$text) +
  scale_fill_gradient(
    low = "#cbd5e1", high = PAL$diverge_hi,
    guide = "none"
  ) +
  scale_x_continuous(breaks = scales::pretty_breaks(6),
                     expand = expansion(mult = c(0, 0.35))) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.4) +
  annotate("text", x = league_avg, y = n_rows + 0.8,
           label = sprintf("league avg (%.1f)", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "2026 WR schedule strength: who faces the toughest CB rooms?",
    subtitle = paste0(
      "Each team's WR1 (by blended FC/KTC/LR dynasty value) shown alongside ",
      "their schedule's average opposing CB unit score. All WRs on a team share ",
      "the same 17-game slate, so this is a team-level outlook with the headline WR surfaced."
    ),
    x        = "Average opponent CB unit score",
    y        = NULL,
    caption  = "Data: PFR adv-def via nflreadr · WR rankings: FantasyCalc + KeepTradeCut + LateRound · logos & headshots: nflplotR"
  ) +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/cb_wr_matchup/wr_schedule.png"),
           width = 14, height = 14)
