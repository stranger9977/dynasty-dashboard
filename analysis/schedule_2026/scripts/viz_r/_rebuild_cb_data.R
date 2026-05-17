## Rebuild cb_wr_matchup parquets with new PFR+PBP composite.
##
## Reads existing depth chart (CB1/CB2/Nickel names per team) from
## output/cb_wr_matchup/data.parquet, then rescores using build_cb_quality().
## Re-derives wr_schedules.parquet and marquee_matchups.parquet on top.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")
CB_QUALITY_NO_RUN <- TRUE  # prevent _cb_quality.R from running its example block
source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_cb_quality.R")

OUT_DIR <- file.path(PROJ_ROOT, "output/cb_wr_matchup")

# Old data (depth chart by team)
old_team   <- read_parquet(file.path(OUT_DIR, "data.parquet"))
old_wr     <- read_parquet(file.path(OUT_DIR, "wr_schedules.parquet"))
old_marq   <- read_parquet(file.path(OUT_DIR, "marquee_matchups.parquet"))

cat("Old top CB units:\n")
print(head(old_team[order(-old_team$unit_score), c("team","cb1_name","cb2_name","nickel_name","unit_score")], 5))

# Build new CB quality table
qual <- build_cb_quality()

# Score each slot
slot_names <- c("cb1_name", "cb2_name", "nickel_name")
slot_scores <- c("cb1_score", "cb2_score", "nickel_score")

new_team <- old_team
match_info <- list()
for (i in seq_along(slot_names)) {
  res <- cb_score_for(new_team[[slot_names[i]]], qual)
  new_team[[slot_scores[i]]] <- res$score
  match_info[[slot_names[i]]] <- res$matched
}
matched_total  <- sum(unlist(match_info))
slots_total    <- 3 * nrow(new_team)
cat(sprintf("\nMatched %d / %d CB slots (%.0f%%)\n",
            matched_total, slots_total, 100 * matched_total / slots_total))

# Recompute team unit score
new_team$unit_score <- with(new_team,
                            round(0.45 * cb1_score + 0.35 * cb2_score + 0.20 * nickel_score, 1))

cat("\nNew top 5 CB units:\n")
print(head(new_team[order(-new_team$unit_score), c("team","cb1_name","cb1_score","cb2_name","cb2_score","nickel_name","nickel_score","unit_score")], 5))

cat("\nNew bottom 5 CB units:\n")
print(head(new_team[order(new_team$unit_score), c("team","cb1_name","cb1_score","cb2_name","cb2_score","nickel_name","nickel_score","unit_score")], 5))

# Rank shifts vs old
rank_old <- rank(-old_team$unit_score)
rank_new <- rank(-new_team$unit_score)
shifts <- data.frame(team = old_team$team,
                     old_rank = rank_old,
                     new_rank = rank_new,
                     old_score = old_team$unit_score,
                     new_score = new_team$unit_score,
                     delta_rank = rank_old - rank_new)  # positive = improved
cat("\nLargest rank shifts (positive = improved):\n")
print(shifts[order(-abs(shifts$delta_rank)), ][1:10, ])

# WR schedules — recompute using new unit scores
# Reuse old WR list (96 WRs), but recompute total_opp_cb_score using new unit_map
unit_map <- setNames(new_team$unit_score, new_team$team)

games <- read.csv(file.path(PROJ_ROOT, "data/raw/games.csv"), stringsAsFactors = FALSE)
games <- games[games$season == 2026 & games$game_type == "REG", ]
opp_long <- dplyr::bind_rows(
  data.frame(team = games$home_team, opp = games$away_team),
  data.frame(team = games$away_team, opp = games$home_team)
)

new_wr <- old_wr |>
  dplyr::rowwise() |>
  dplyr::mutate(
    opps   = list(opp_long$opp[opp_long$team == team]),
    n_games = length(opps),
    total_opp_cb_score = round(sum(unit_map[opps], na.rm = TRUE), 1),
    avg_opp_cb_score   = round(total_opp_cb_score / n_games, 2)
  ) |>
  dplyr::ungroup() |>
  dplyr::select(wr_name, team, n_games, total_opp_cb_score, avg_opp_cb_score) |>
  dplyr::arrange(desc(avg_opp_cb_score))

# Marquee matchups — rebuild from scratch
# (the old parquet has only top-18 already, so we recompute from merged.parquet)
TEAM_FIX <- c("GBP" = "GB", "KCC" = "KC", "LVR" = "LV", "NOS" = "NO",
              "SFO" = "SF", "TBB" = "TB", "LAR" = "LA")
wrs_all <- read_parquet("/Users/nick/projects/dynasty-dashboard/data/merged.parquet") |>
  dplyr::filter(position == "WR", team != "FA") |>
  dplyr::mutate(team = ifelse(team %in% names(TEAM_FIX), TEAM_FIX[team], team)) |>
  dplyr::select(name, team, blended_value)

top40 <- wrs_all |>
  dplyr::arrange(dplyr::desc(blended_value)) |>
  dplyr::slice_head(n = 40)

# All (week, team, opp) combos for 2026
schedule_long <- dplyr::bind_rows(
  data.frame(week = games$week, team = games$home_team, opp = games$away_team),
  data.frame(week = games$week, team = games$away_team, opp = games$home_team)
)

candidates <- top40 |>
  dplyr::inner_join(schedule_long, by = "team") |>
  dplyr::mutate(cb_unit = unname(unit_map[opp])) |>
  dplyr::mutate(marquee_score = blended_value * cb_unit / 100) |>
  dplyr::arrange(dplyr::desc(marquee_score))

# Dedupe by (name, opp) keeping highest scoring week, then top 18
new_marq <- candidates |>
  dplyr::distinct(name, opp, .keep_all = TRUE) |>
  dplyr::slice_head(n = 18) |>
  dplyr::select(name, team, week, opp, blended_value, cb_unit, marquee_score) |>
  dplyr::mutate(
    blended_value = round(blended_value, 5),
    cb_unit       = round(cb_unit, 1),
    marquee_score = round(marquee_score, 5)
  )

# Persist
write_parquet(new_team, file.path(OUT_DIR, "data.parquet"))
write_parquet(new_wr,   file.path(OUT_DIR, "wr_schedules.parquet"))
write_parquet(new_marq, file.path(OUT_DIR, "marquee_matchups.parquet"))

cat("\n[ok] rewrote data.parquet, wr_schedules.parquet, marquee_matchups.parquet\n")
