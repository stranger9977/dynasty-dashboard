## Per-position schedule strength — parameterized by env var POSITION.
##   POSITION=RB → output/position_schedules/rb_schedule.png
##   POSITION=TE → output/position_schedules/te_schedule.png
## Bar = team's avg opponent FPA-allowed for that position (percentile within league).
## Higher = tougher schedule. Headshot = top dynasty-value player at the position.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

pos <- Sys.getenv("POSITION", unset = "RB")
stopifnot(pos %in% c("RB", "TE", "QB"))

cfg <- list(
  RB = list(in_file = "rb_schedule.parquet", out = "rb_schedule.png",
            long = "running backs", def = "run defenses"),
  TE = list(in_file = "te_schedule.parquet", out = "te_schedule.png",
            long = "tight ends",    def = "TE defenses"),
  QB = list(in_file = "qb_schedule.parquet", out = "qb_schedule.png",
            long = "quarterbacks",  def = "pass defenses")
)[[pos]]
input_file <- cfg$in_file
output_file <- cfg$out
pos_long <- cfg$long
defense_label <- cfg$def

d <- read_parquet(file.path(PROJ_ROOT, "output/position_schedules", input_file))

# Resolve gsis_id for headshots
gsis <- resolve_gsis(d$top_player, position = pos, team = d$team)
d$gsis_id <- gsis$gsis_id

d <- d |>
  dplyr::arrange(sos_score) |>
  dplyr::mutate(team = factor(team, levels = team))

league_avg <- mean(d$sos_score)
n_rows <- length(levels(d$team))

p <- ggplot(d, aes(y = team, x = sos_score)) +
  geom_col(aes(fill = sos_score), width = 0.78, colour = NA) +
  geom_text(aes(label = sprintf("%.0f  ·  %s  (opp avg %.1f FPA)",
                                sos_score, top_player, opp_fpa)),
            hjust = -0.07, size = 3.4, colour = PAL$text) +
  scale_fill_gradient(
    low = "#cbd5e1", high = PAL$diverge_hi,
    guide = "none"
  ) +
  scale_x_continuous(breaks = seq(0, 100, by = 20),
                     limits = c(0, 110),
                     expand = expansion(0)) +
  geom_vline(xintercept = league_avg, linetype = "31",
             colour = PAL$muted, linewidth = 0.4) +
  annotate("text", x = league_avg, y = n_rows + 0.8,
           label = sprintf("league avg (%.0f)", league_avg),
           hjust = 0.5, colour = PAL$muted, size = 3.4) +
  coord_cartesian(clip = "off") +
  labs(
    title    = sprintf("2026 %s schedule strength: who faces the toughest %s?", pos, defense_label),
    subtitle = sprintf(
      "Each team's top dynasty %s shown alongside their schedule's average opposing %s-FPA-allowed (percentile within league). Higher = tougher schedule.",
      pos, pos
    ),
    x        = sprintf("Opponent %s-FPA percentile (0 = softest schedule, 100 = toughest)", pos),
    y        = NULL,
    caption  = "FPA from nflverse PBP 2023-25 (recency-weighted 50/30/20) · player rankings: FantasyCalc + KeepTradeCut + LateRound · logos: nflplotR"
  ) +
  theme_sched(14) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 1.0),
    axis.ticks.y        = element_blank(),
    panel.grid.major.y  = element_blank()
  )

save_chart(p, file.path(PROJ_ROOT, "output/position_schedules", output_file),
           width = 16, height = 14)
