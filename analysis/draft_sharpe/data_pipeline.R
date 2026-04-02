# NFL Draft Quasi-Sharpe Ratio — Data Pipeline
# Pulls nflreadr data, joins draft picks with snap counts and contracts,
# classifies hits, computes Sharpe ratio components, exports parquet.

library(nflreadr)
library(tidyverse)
library(arrow)

cat("Draft Sharpe data pipeline\n")
cat("=========================\n\n")

# --- Constants ---------------------------------------------------------------

POSITION_MAP <- c(
  "QB" = "QB",
  "RB" = "RB", "FB" = "RB",
  "WR" = "WR",
  "TE" = "TE",
  "T" = "OT", "OT" = "OT", "LT" = "OT", "RT" = "OT",
  "G" = "IOL", "C" = "IOL", "OL" = "IOL", "OG" = "IOL", "LG" = "IOL", "RG" = "IOL",
  "DE" = "EDGE", "OLB" = "EDGE", "EDGE" = "EDGE", "ED" = "EDGE",
  "DT" = "DL", "NT" = "DL", "DL" = "DL", "IDL" = "DL",
  "LB" = "LB", "ILB" = "LB", "MLB" = "LB",
  "CB" = "CB", "DB" = "CB",
  "S" = "S", "SS" = "S", "FS" = "S"
)

TIER_BREAKS <- c(0, 10, 32, 64, 100, Inf)
TIER_LABELS <- c("Top 10", "Late 1st", "Day 2", "Day 3 Early", "Day 3 Late")

# PFF hit thresholds: 2/3 of positional baseline snap %
HIT_THRESHOLDS <- tibble::tibble(
  pos_group = c("IOL", "OT", "S", "LB", "CB", "WR", "QB", "EDGE", "DL", "TE", "RB"),
  hit_threshold = c(0.664, 0.649, 0.635, 0.615, 0.615, 0.569, 0.553, 0.541, 0.478, 0.475, 0.376)
)

ROOKIE_DEAL_YEARS <- 4  # First 4 seasons for snap evaluation

# --- 1. Draft Picks ----------------------------------------------------------

cat("Loading draft picks...\n")
draft_raw <- load_draft_picks(seasons = TRUE)

draft <- draft_raw |>
  filter(!is.na(position)) |>
  mutate(
    pos_group = POSITION_MAP[position],
    tier = cut(pick, breaks = TIER_BREAKS, labels = TIER_LABELS, right = TRUE)
  ) |>
  filter(!is.na(pos_group)) |>
  select(
    season, round, pick, team, pfr_player_id, gsis_id,
    pfr_player_name, position, pos_group, tier,
    games, seasons_started, allpro, probowls, w_av, car_av
  )

cat(sprintf("  %d draft picks loaded (%d-%d)\n", nrow(draft), min(draft$season), max(draft$season)))
cat(sprintf("  Position groups: %s\n", paste(sort(unique(draft$pos_group)), collapse = ", ")))

# --- 2. Snap Counts (first 4 seasons) ----------------------------------------

cat("Loading snap counts (2012+)...\n")
snaps_raw <- load_snap_counts(seasons = TRUE)

cat(sprintf("  Snap count seasons available: %d-%d\n",
            min(snaps_raw$season), max(snaps_raw$season)))

snap_min_season <- min(snaps_raw$season)

draft_with_snap_window <- draft |>
  filter(season >= snap_min_season - ROOKIE_DEAL_YEARS + 1) |>
  mutate(
    snap_start = season,
    snap_end = season + ROOKIE_DEAL_YEARS - 1
  )

offensive_groups <- c("QB", "RB", "WR", "TE", "OT", "IOL")
defensive_groups <- c("EDGE", "DL", "LB", "CB", "S")

snaps_agg <- snaps_raw |>
  select(season, week, pfr_player_id, offense_pct, defense_pct) |>
  inner_join(
    draft_with_snap_window |> select(pfr_player_id, snap_start, snap_end, pos_group),
    by = "pfr_player_id"
  ) |>
  filter(season >= snap_start, season <= snap_end) |>
  mutate(
    snap_pct = if_else(pos_group %in% offensive_groups, offense_pct, defense_pct)
  ) |>
  group_by(pfr_player_id) |>
  summarise(
    avg_snap_pct = mean(snap_pct, na.rm = TRUE),
    total_games_snapped = n(),
    seasons_with_snaps = n_distinct(season),
    .groups = "drop"
  )

cat(sprintf("  Aggregated snap data for %d players\n", nrow(snaps_agg)))

# --- 3. Hit Classification ----------------------------------------------------

cat("Classifying hits...\n")

draft_snaps <- draft_with_snap_window |>
  left_join(snaps_agg, by = "pfr_player_id") |>
  left_join(HIT_THRESHOLDS, by = "pos_group") |>
  mutate(
    avg_snap_pct = replace_na(avg_snap_pct, 0),
    is_hit = avg_snap_pct >= hit_threshold
  )

hit_summary <- draft_snaps |>
  group_by(pos_group) |>
  summarise(
    n = n(),
    hits = sum(is_hit),
    hit_rate = mean(is_hit),
    .groups = "drop"
  ) |>
  arrange(desc(hit_rate))

cat("\n  Overall hit rates by position:\n")
print(hit_summary, n = Inf)

# --- 4. Contracts -------------------------------------------------------------

cat("Loading contracts...\n")
contracts_raw <- load_contracts()

contracts <- contracts_raw |>
  mutate(pos_group = POSITION_MAP[position]) |>
  filter(!is.na(pos_group), !is.na(apy_cap_pct))

cat(sprintf("  %d contracts loaded\n", nrow(contracts)))

# --- 5. Second Contracts (post-rookie deal) -----------------------------------

cat("Matching second contracts to drafted players...\n")

second_contracts <- draft_snaps |>
  select(pfr_player_id, pfr_player_name, season, pos_group) |>
  inner_join(
    contracts |> select(player, otc_id, year_signed, apy_cap_pct, apy, value, years, pos_group),
    by = "pos_group",
    relationship = "many-to-many"
  ) |>
  filter(
    str_to_lower(str_trim(pfr_player_name)) == str_to_lower(str_trim(player)),
    year_signed >= season + ROOKIE_DEAL_YEARS,
    year_signed <= season + ROOKIE_DEAL_YEARS + 2
  ) |>
  group_by(pfr_player_id) |>
  slice_min(year_signed, n = 1, with_ties = FALSE) |>
  ungroup() |>
  select(pfr_player_id, second_apy_cap_pct = apy_cap_pct,
         second_contract_year = year_signed, second_contract_apy = apy,
         second_contract_value = value, second_contract_years = years)

cat(sprintf("  Matched %d second contracts\n", nrow(second_contracts)))

# --- 6. Free Agency Replacement Cost ------------------------------------------

cat("Computing FA replacement cost by position...\n")

fa_replacement <- contracts |>
  filter(apy_cap_pct > 0.001) |>
  group_by(pos_group) |>
  summarise(
    fa_median_apy_cap_pct = median(apy_cap_pct, na.rm = TRUE),
    fa_mean_apy_cap_pct = mean(apy_cap_pct, na.rm = TRUE),
    fa_n = n(),
    .groups = "drop"
  )

cat("\n  FA replacement cost (median apy_cap_pct) by position:\n")
print(fa_replacement, n = Inf)

# --- 7. Final Join ------------------------------------------------------------

cat("Building final analysis dataset...\n")

analysis_df <- draft_snaps |>
  left_join(second_contracts, by = "pfr_player_id") |>
  left_join(fa_replacement, by = "pos_group") |>
  mutate(
    second_apy_cap_pct = replace_na(second_apy_cap_pct, 0)
  )

cat(sprintf("  Final dataset: %d players\n", nrow(analysis_df)))

# --- 8. Sharpe Ratio Computation ----------------------------------------------

cat("Computing Sharpe ratios...\n")

elite_threshold <- quantile(
  analysis_df$second_apy_cap_pct[analysis_df$second_apy_cap_pct > 0],
  probs = 0.90, na.rm = TRUE
)
cat(sprintf("  Elite threshold (90th pctl of non-zero): %.4f apy_cap_pct\n", elite_threshold))

sharpe_ratios <- analysis_df |>
  group_by(pos_group, tier) |>
  summarise(
    n = n(),
    hit_rate = mean(is_hit),
    mean_second_contract = mean(second_apy_cap_pct, na.rm = TRUE),
    sd_second_contract = sd(second_apy_cap_pct, na.rm = TRUE),
    elite_prob = mean(second_apy_cap_pct >= elite_threshold, na.rm = TRUE),
    fa_replacement = first(fa_median_apy_cap_pct),
    .groups = "drop"
  ) |>
  mutate(
    sharpe_linear = (mean_second_contract - fa_replacement) / sd_second_contract,
    sharpe_elite = (elite_prob * elite_threshold - fa_replacement) / sd_second_contract
  ) |>
  mutate(
    across(starts_with("sharpe_"), ~ if_else(is.finite(.x), .x, NA_real_))
  )

cat("\n  Sharpe ratios (linear):\n")
sharpe_ratios |>
  select(pos_group, tier, n, hit_rate, sharpe_linear, sharpe_elite) |>
  arrange(pos_group, tier) |>
  print(n = Inf)

# --- 9. Export ----------------------------------------------------------------

cat("\nExporting parquet...\n")
write_parquet(analysis_df, "data/draft_sharpe_analysis.parquet")

dir.create("output", showWarnings = FALSE)
write_csv(sharpe_ratios, "output/sharpe_ratios.csv")

hit_rates_export <- analysis_df |>
  group_by(pos_group, tier) |>
  summarise(n = n(), hits = sum(is_hit), hit_rate = mean(is_hit), .groups = "drop")
write_csv(hit_rates_export, "output/hit_rates.csv")

write_csv(fa_replacement, "output/fa_replacement.csv")

player_lookup <- analysis_df |>
  select(pfr_player_name, pos_group, season, pick, tier,
         is_hit, avg_snap_pct, second_apy_cap_pct) |>
  left_join(
    sharpe_ratios |> select(pos_group, tier, sharpe_linear, sharpe_elite),
    by = c("pos_group", "tier")
  ) |>
  arrange(desc(season), pick)
write_csv(player_lookup, "output/player_lookup.csv")

cat("Done! Outputs:\n")
cat("  data/draft_sharpe_analysis.parquet\n")
cat("  output/sharpe_ratios.csv\n")
cat("  output/hit_rates.csv\n")
cat("  output/fa_replacement.csv\n")
cat("  output/player_lookup.csv\n")
