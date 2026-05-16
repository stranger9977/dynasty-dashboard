# Late Round Prospect Guide — Evaluation Data Pipeline
# Pulls nflreadr data, joins to harmonized guide players, builds eval_df.
#
# Usage:
#   Rscript analysis/late_round_eval/data_pipeline.R
#
# Outputs:
#   analysis/late_round_eval/data/{draft_picks,rosters,player_stats}.parquet
#   analysis/late_round_eval/extraction/output/nfl_universe.parquet
#   analysis/late_round_eval/data/eval_df.parquet

suppressPackageStartupMessages({
  library(nflreadr)
  library(tidyverse)
  library(arrow)
})

DATA_DIR <- "analysis/late_round_eval/data"
EXTRACT_DIR <- "analysis/late_round_eval/extraction/output"
dir.create(DATA_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(EXTRACT_DIR, recursive = TRUE, showWarnings = FALSE)

EVAL_CLASSES <- 2022:2025
# Need up to 3 yrs post-draft for 2022 → 2024; 2025 → 2025 only. We clamp to
# the latest season nflreadr has, which lags real-world calendar in the offseason.
STAT_SEASONS <- 2022:min(2026, nflreadr::most_recent_season())

# --- Helpers ----------------------------------------------------------------

normalize_name <- function(x) {
  x |>
    str_to_lower() |>
    str_replace_all("[\\.,'\\-]", "") |>
    str_remove_all("\\b(jr|sr|ii|iii|iv|v)\\b") |>
    str_replace_all("\\s+", " ") |>
    str_trim()
}

classify_draft_round <- function(round) {
  case_when(
    is.na(round) ~ "UDFA",
    round == 1 ~ "1",
    round == 2 ~ "2",
    round == 3 ~ "3",
    round %in% 4:7 ~ "day-3",
    TRUE ~ NA_character_
  )
}

# P5 conferences by year (Pac-12 collapsed after 2023)
P5_BY_YEAR <- list(
  `2022` = c("SEC", "Big Ten", "Big 12", "ACC", "Pac-12"),
  `2023` = c("SEC", "Big Ten", "Big 12", "ACC", "Pac-12"),
  `2024` = c("SEC", "Big Ten", "Big 12", "ACC"),
  `2025` = c("SEC", "Big Ten", "Big 12", "ACC"),
  `2026` = c("SEC", "Big Ten", "Big 12", "ACC")
)

# College → conference lookup. Hardcoded for known programs.
# Notre Dame is always P5 (independent but treated as P5).
COLLEGE_CONFERENCE <- tibble::tribble(
  ~college,           ~conference,
  "Alabama",          "SEC",
  "Georgia",          "SEC",
  "LSU",              "SEC",
  "Florida",          "SEC",
  "Tennessee",        "SEC",
  "Auburn",           "SEC",
  "Arkansas",         "SEC",
  "Kentucky",         "SEC",
  "Mississippi",      "SEC",
  "Mississippi State","SEC",
  "Missouri",         "SEC",
  "South Carolina",   "SEC",
  "Texas A&M",        "SEC",
  "Vanderbilt",       "SEC",
  "Texas",            "SEC",        # joined 2024
  "Oklahoma",         "SEC",        # joined 2024
  "Ohio State",       "Big Ten",
  "Michigan",         "Big Ten",
  "Penn State",       "Big Ten",
  "Wisconsin",        "Big Ten",
  "Iowa",             "Big Ten",
  "Minnesota",        "Big Ten",
  "Illinois",         "Big Ten",
  "Indiana",          "Big Ten",
  "Purdue",           "Big Ten",
  "Michigan State",   "Big Ten",
  "Nebraska",         "Big Ten",
  "Maryland",         "Big Ten",
  "Rutgers",          "Big Ten",
  "Northwestern",     "Big Ten",
  # Pac-12 schools that moved to Big Ten in 2024 (still P5).
  "USC",              "Big Ten",
  "UCLA",             "Big Ten",
  "Oregon",           "Big Ten",
  "Washington",       "Big Ten",
  "Oklahoma State",   "Big 12",
  "Kansas",           "Big 12",
  "Kansas State",     "Big 12",
  "Iowa State",       "Big 12",
  "TCU",              "Big 12",
  "Baylor",           "Big 12",
  "Texas Tech",       "Big 12",
  "West Virginia",    "Big 12",
  "BYU",              "Big 12",
  "Cincinnati",       "Big 12",
  "Houston",          "Big 12",
  "UCF",              "Big 12",
  # Pac-12 schools that moved to Big 12 in 2024 (still P5).
  "Arizona",          "Big 12",
  "Arizona State",    "Big 12",
  "Colorado",         "Big 12",
  "Utah",             "Big 12",
  "Clemson",          "ACC",
  "Florida State",    "ACC",
  "Miami",            "ACC",
  "North Carolina",   "ACC",
  "NC State",         "ACC",
  "Duke",             "ACC",
  "Wake Forest",      "ACC",
  "Virginia",         "ACC",
  "Virginia Tech",    "ACC",
  "Louisville",       "ACC",
  "Pittsburgh",       "ACC",
  "Boston College",   "ACC",
  "Syracuse",         "ACC",
  "Georgia Tech",     "ACC",
  # Pac-12 schools that moved to ACC in 2024 (still P5).
  "California",       "ACC",
  "Stanford",         "ACC",
  # SMU was AAC pre-2024, ACC from 2024+. Mapped to ACC (current); this
  # slightly over-credits pre-2024 SMU products, but P5/non-P5 is a coarse
  # marker and current-conference is the simplest defensible model.
  "SMU",              "ACC",
  # Oregon State and Washington State stayed in the rump Pac-12 and lost
  # P5 status from 2024 onward.
  "Oregon State",     "Pac-12",
  "Washington State", "Pac-12",
  "Notre Dame",       "Independent" # always treat as P5
)

# Synonyms / abbreviations for schools whose name in the guide differs
# from the canonical short form used in COLLEGE_CONFERENCE.
COLLEGE_SYNONYMS <- c(
  "southern california" = "USC",
  "louisiana state"     = "LSU",
  "texas christian"     = "TCU",
  "southern methodist"  = "SMU",
  "brigham young"       = "BYU",
  "ole miss"            = "Mississippi",
  "miami fl"            = "Miami",
  "miami florida"       = "Miami",
  "central florida"     = "UCF",
  "north carolina state"= "NC State",
  "alabama birmingham"  = "UAB"
)

# Common mascot tokens that appear after the school name in some guide
# extractions (e.g., "Alabama Crimson Tide"). Stripped before lookup.
.MASCOT_TOKENS <- c(
  "Crimson Tide", "Bulldogs", "Tigers", "Wildcats", "Buckeyes", "Wolverines",
  "Gators", "Razorbacks",
  "Nittany Lions", "Badgers", "Hawkeyes", "Gophers", "Fighting Illini",
  "Illini", "Hoosiers", "Boilermakers", "Spartans", "Cornhuskers",
  "Terrapins", "Scarlet Knights", "Trojans", "Bruins", "Ducks", "Huskies",
  "Beavers", "Cougars", "Sun Devils", "Buffaloes", "Utes", "Cardinal",
  "Razorbacks", "Volunteers", "Commodores", "Rebels", "Gamecocks",
  "Aggies", "Longhorns", "Sooners", "Cyclones", "Jayhawks", "Mountaineers",
  "Bearcats", "Red Raiders", "Horned Frogs", "Knights", "Mustangs",
  "Buffaloes", "Demon Deacons", "Cavaliers", "Hokies", "Tar Heels",
  "Yellow Jackets", "Hurricanes", "Orange", "Eagles", "Panthers",
  "Seminoles", "Cardinals", "Fighting Irish", "Bears", "Owls", "Broncos",
  "Mustangs", "Aztecs", "Lobos", "Falcons", "Rebels", "Mean Green",
  "Roadrunners", "Pirates", "Chanticleers", "Thundering Herd",
  "Green Wave", "Mocs", "Bison", "Jackrabbits", "Pioneers",
  "Hilltoppers", "Hilltoppers", "Coyotes", "Hatters", "Argonauts",
  "Catamounts", "Crusaders", "Hawks", "Spiders", "Phoenix", "Highlanders",
  "Greyhounds", "Royals", "Penguins", "Bulls", "Mounties", "Cajuns",
  "Sharks", "Anteaters", "Wolf Pack", "Aggies", "Bobcats", "Lumberjacks",
  "Sycamores", "Salukis", "Redbirds", "Leathernecks", "Bengals",
  "Quakers", "Bantams", "Statesmen", "Engineers", "Patriots",
  "Minutemen", "Black Bears", "Catamounts", "Crusaders", "Lakers",
  "Toreros", "Aggies", "Tritons", "Vandals", "Owls", "Golden Eagles",
  "Redhawks"
)

canonicalize_college <- function(college) {
  if (is.na(college) || college == "") return(NA_character_)
  s <- college
  # Strip mascot tokens first (try longest first to avoid partial matches)
  for (mascot in .MASCOT_TOKENS[order(-nchar(.MASCOT_TOKENS))]) {
    pattern <- paste0(" ", mascot, "$")
    s <- str_remove(s, regex(pattern, ignore_case = TRUE))
  }
  s <- str_trim(s)
  # Then synonym lookup on the mascot-stripped form (case-insensitive)
  key <- str_to_lower(str_replace_all(s, "[\\.,'\\-]", " ")) |> str_squish()
  syn <- COLLEGE_SYNONYMS[key]
  if (!is.na(syn)) return(unname(syn))
  s
}

p5_flag <- function(college, year) {
  year_key <- as.character(year)
  p5_confs <- P5_BY_YEAR[[year_key]]
  # Canonicalize each input (vectorized via sapply for use in mutate(mapply(...)))
  canon <- vapply(college, canonicalize_college, character(1))
  conf <- COLLEGE_CONFERENCE$conference[match(canon, COLLEGE_CONFERENCE$college)]
  ifelse(canon == "Notre Dame", TRUE,
         ifelse(!is.na(conf) & conf %in% p5_confs, TRUE, FALSE))
}

compute_best_ffppg <- function(stats, draft_year_lookup, max_years = 3) {
  # stats: long df with player_id, season, fantasy_points_ppr, games
  # draft_year_lookup: tibble (player_id, draft_year) OR named numeric vector
  if (inherits(draft_year_lookup, "data.frame")) {
    dy <- draft_year_lookup
  } else if (is.atomic(draft_year_lookup) && !is.null(names(draft_year_lookup))) {
    dy <- tibble(player_id = names(draft_year_lookup),
                 draft_year = as.integer(unname(draft_year_lookup)))
  } else {
    stop("draft_year_lookup must be a data.frame or named numeric vector")
  }
  stats |>
    left_join(dy, by = "player_id") |>
    mutate(years_post = season - draft_year + 1) |>
    filter(years_post >= 1, years_post <= max_years, games > 0) |>
    mutate(ffppg = fantasy_points_ppr / games) |>
    group_by(player_id) |>
    summarise(best_ffppg = max(ffppg, na.rm = TRUE), .groups = "drop")
}

# --- Pulls ------------------------------------------------------------------

pull_data <- function() {
  cat("Pulling draft picks (2022-2026)...\n")
  draft_picks <- load_draft_picks(seasons = EVAL_CLASSES) |>
    select(season, round, pick, pfr_player_id, gsis_id,
           full_name = pfr_player_name, position, team, college)
  write_parquet(draft_picks, file.path(DATA_DIR, "draft_picks.parquet"))

  cat("Pulling rosters (2022-2026)...\n")
  rosters <- load_rosters(seasons = EVAL_CLASSES) |>
    select(season, gsis_id, full_name, position, birth_date,
           entry_year, draft_number, college) |>
    distinct(gsis_id, .keep_all = TRUE)
  write_parquet(rosters, file.path(DATA_DIR, "rosters.parquet"))

  cat("Pulling weekly player stats (2022-2026)...\n")
  # stat_type is deprecated in nflreadr 1.5.0+; load_player_stats now returns
  # offense by default. We filter to WR/RB after.
  player_stats <- load_player_stats(seasons = STAT_SEASONS) |>
    filter(position %in% c("WR", "RB")) |>
    select(player_id, player_name, position, season, week, fantasy_points_ppr)
  write_parquet(player_stats, file.path(DATA_DIR, "player_stats.parquet"))

  cat("Done with pulls.\n")
}

build_nfl_universe <- function() {
  # Union of drafted players + UDFA rookies from rosters for EVAL_CLASSES
  draft_picks <- read_parquet(file.path(DATA_DIR, "draft_picks.parquet"))
  rosters <- read_parquet(file.path(DATA_DIR, "rosters.parquet"))

  drafted <- draft_picks |>
    filter(position %in% c("WR", "RB")) |>
    inner_join(rosters |> select(gsis_id, birth_date), by = "gsis_id") |>
    transmute(
      player_id = gsis_id,
      name = full_name,
      position,
      birth_date,
      draft_year = season,
      draft_pick = pick,
      college
    )

  # UDFAs: rookies in rosters with no draft pick, first season ∈ EVAL_CLASSES
  udfa <- rosters |>
    filter(position %in% c("WR", "RB"),
           is.na(draft_number),
           entry_year %in% EVAL_CLASSES) |>
    transmute(
      player_id = gsis_id,
      name = full_name,
      position,
      birth_date,
      draft_year = entry_year,
      draft_pick = 300L,   # UDFA placeholder
      college
    )

  nfl <- bind_rows(drafted, udfa) |> distinct(player_id, .keep_all = TRUE)
  write_parquet(nfl, file.path(EXTRACT_DIR, "nfl_universe.parquet"))
  cat("nfl_universe.parquet:", nrow(nfl), "rows\n")
  nfl
}

build_eval_df <- function() {
  matches <- read_parquet(file.path(EXTRACT_DIR, "matches.parquet"))
  player_stats <- read_parquet(file.path(DATA_DIR, "player_stats.parquet"))

  # Aggregate weekly → season FFPPG
  season_stats <- player_stats |>
    group_by(player_id, season) |>
    summarise(
      fantasy_points_ppr = sum(fantasy_points_ppr, na.rm = TRUE),
      games = n_distinct(week),
      .groups = "drop"
    )

  # matches already contains player_id, draft_year, draft_pick, birth_date
  # from the NFL side of the funnel join.
  draft_year_lookup <- matches |> distinct(player_id, draft_year)
  best_ffppg <- compute_best_ffppg(season_stats, draft_year_lookup, max_years = 3)

  eval_df <- matches |>
    left_join(best_ffppg, by = "player_id") |>
    mutate(
      age = as.numeric(difftime(as.Date(paste0(draft_year, "-09-01")),
                                as.Date(birth_date), units = "days")) / 365.25,
      draft_round = classify_draft_round(
        # back out round from pick; pick 300 = UDFA
        case_when(draft_pick == 300 ~ NA_integer_,
                  draft_pick <= 32 ~ 1L,
                  draft_pick <= 64 ~ 2L,
                  draft_pick <= 96 ~ 3L,
                  draft_pick <= 224 ~ as.integer(ceiling(draft_pick / 32)),
                  TRUE ~ 7L)
      ),
      p5_flag = mapply(p5_flag, college, guide_year),
      best_ffppg = replace_na(best_ffppg, 0),
      hit_flag = best_ffppg >= 10,
      elite_flag = best_ffppg >= 15,
      bust_flag = best_ffppg < 5,
      eval_window = if_else(guide_year == 2025, "Y1-only", "Y1-Y3"),
      canonical_tier = factor(canonical_tier,
                              levels = c("Dart Throw", "Depth", "Flex", "Starter", "Elite"),
                              ordered = TRUE)
    ) |>
    filter(guide_year %in% EVAL_CLASSES)  # exclude 2026

  write_parquet(eval_df, file.path(DATA_DIR, "eval_df.parquet"))
  cat("eval_df.parquet:", nrow(eval_df), "rows\n")
  print(eval_df |> count(position, canonical_tier))
  eval_df
}

# --- Main -------------------------------------------------------------------

if (!interactive() && sys.nframe() == 0) {
  pull_data()
  build_nfl_universe()
  if (file.exists(file.path(EXTRACT_DIR, "matches.parquet"))) {
    build_eval_df()
  } else {
    cat("matches.parquet not found — run Task 10 matching before eval_df build.\n")
  }
}
