## Rebuild CB-quality composite using PFR advstats (def) + PBP counting stats.
##
## Composite per CB:
##   - PFR component (z-scored within qualified CB pool, then mapped to [0,100]):
##       * 40% inverse passer rating allowed  (-rat)
##       * 25% inverse completion % allowed   (-cmp_percent)
##       * 15% (INTs + PDs) / target          ((int + pd) / tgt)    [pd via PBP fallback]
##   - PBP counting component (15%):
##       * PDs/game (60%), INTs/game (40%) — recency-weighted 2025=0.6, 2024=0.4
##   - FTN: unavailable at the defender level in free release — skipped.
## Final = 0.80 * pfr_perc + 0.20 * pbp_perc, then percentile-renormalized.
##
## Outputs a tibble with cols:
##   gsis_id (may be NA), pfr_id, player_name, qualifying, quality_score, components.
##
## Run standalone with:  Rscript scripts/viz_r/_cb_quality.R

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

build_cb_quality <- function() {
  message("[cb_quality] loading PFR advstats (def) for 2024+2025 ...")
  pfr_24 <- nflreadr::load_pfr_advstats(seasons = 2024, stat_type = "def",
                                        summary_level = "season")
  pfr_25 <- nflreadr::load_pfr_advstats(seasons = 2025, stat_type = "def",
                                        summary_level = "season")

  message("[cb_quality] PFR rows: 2024=", nrow(pfr_24), " 2025=", nrow(pfr_25))

  # Recency weights
  W <- c(`2024` = 0.4, `2025` = 0.6)

  # Filter to CB-eligible roles; PFR uses DB/CB position codes.
  cb_filter <- function(d) d[d$pos %in% c("CB", "DB", "LCB", "RCB", "DC", "S", "NB"), , drop = FALSE]

  pfr <- dplyr::bind_rows(
    pfr_24 |> dplyr::mutate(season = 2024),
    pfr_25 |> dplyr::mutate(season = 2025)
  )

  # Build per-PFR-player weighted aggregate. Only CB-like positions.
  # We use pfr_id (a PFR slug) as the canonical key here; map to gsis later.
  pfr <- pfr |>
    dplyr::filter(pos %in% c("CB", "DB", "LCB", "RCB", "S", "FS", "SS", "NB"),
                  !is.na(pfr_id), !is.na(tgt), tgt > 0) |>
    dplyr::mutate(w = W[as.character(season)],
                  rat = ifelse(is.na(rat), NA_real_, rat),
                  cmp_percent = ifelse(is.na(cmp_percent), NA_real_, cmp_percent))

  pfr_agg <- pfr |>
    dplyr::group_by(pfr_id, player) |>
    dplyr::summarise(
      tgt_w        = sum(tgt * w, na.rm = TRUE),
      games_w      = sum(g * w, na.rm = TRUE),
      cmp_w        = sum(cmp * w, na.rm = TRUE),
      yds_w        = sum(yds * w, na.rm = TRUE),
      int_w        = sum(int * w, na.rm = TRUE),
      # Weighted average of rate-type metrics, denominator weighted by tgt.
      rat_w_num    = sum(rat * tgt * w, na.rm = TRUE),
      rat_w_denom  = sum(tgt * w * !is.na(rat), na.rm = TRUE),
      cmp_pct_num  = sum(cmp_percent * tgt * w, na.rm = TRUE),
      cmp_pct_denom = sum(tgt * w * !is.na(cmp_percent), na.rm = TRUE),
      .groups = "drop"
    ) |>
    dplyr::mutate(
      passer_rating_allowed = rat_w_num / pmax(rat_w_denom, 1e-9),
      cmp_pct_allowed       = cmp_pct_num / pmax(cmp_pct_denom, 1e-9),
      ints_per_tgt          = int_w / pmax(tgt_w, 1e-9)
    )

  message("[cb_quality] PFR aggregated unique players: ", nrow(pfr_agg))

  # PBP component: load weighted PDs and INTs per game from PBP for the same seasons.
  message("[cb_quality] loading PBP 2024 + 2025 ...")
  pbp_long <- list()
  for (yr in c(2024, 2025)) {
    pbp <- nflreadr::load_pbp(yr)
    pbp <- pbp[pbp$season_type == "REG", ]

    pd_long <- dplyr::bind_rows(
      pbp |> dplyr::filter(!is.na(pass_defense_1_player_id)) |>
        dplyr::transmute(player_id = pass_defense_1_player_id,
                         player_name = pass_defense_1_player_name,
                         game_id, pd = 1, intd = 0),
      pbp |> dplyr::filter(!is.na(pass_defense_2_player_id)) |>
        dplyr::transmute(player_id = pass_defense_2_player_id,
                         player_name = pass_defense_2_player_name,
                         game_id, pd = 1, intd = 0),
      pbp |> dplyr::filter(!is.na(interception_player_id)) |>
        dplyr::transmute(player_id = interception_player_id,
                         player_name = interception_player_name,
                         game_id, pd = 0, intd = 1)
    )

    pbp_long[[as.character(yr)]] <- pd_long |>
      dplyr::group_by(player_id, player_name) |>
      dplyr::summarise(pds = sum(pd), ints = sum(intd),
                       games = dplyr::n_distinct(game_id),
                       .groups = "drop") |>
      dplyr::mutate(season = yr, w = W[as.character(yr)])
  }
  pbp_all <- dplyr::bind_rows(pbp_long) |>
    dplyr::group_by(player_id, player_name) |>
    dplyr::summarise(pds_w  = sum(pds * w),
                     ints_w = sum(ints * w),
                     games_w = sum(games * w),
                     .groups = "drop") |>
    dplyr::mutate(
      pds_pg  = pds_w  / pmax(games_w, 0.5),
      ints_pg = ints_w / pmax(games_w, 0.5)
    )

  message("[cb_quality] PBP aggregated unique players: ", nrow(pbp_all))

  # Build a name->gsis lookup from PFR + rosters (PFR has pfr_id but not gsis).
  # nflreadr's load_rosters gives us pfr_id + gsis_id; use that bridge.
  # IMPORTANT: 2024 rosters often lack pfr_id; prefer 2025 row.
  r24 <- nflreadr::load_rosters(2024)
  r25 <- nflreadr::load_rosters(2025)
  ros <- dplyr::bind_rows(
            r25 |> dplyr::mutate(.src = 2025),
            r24 |> dplyr::mutate(.src = 2024)
         ) |>
    dplyr::filter(!is.na(gsis_id), nchar(gsis_id) > 0) |>
    # Prefer rows that have a pfr_id (the 2025 ones, listed first)
    dplyr::arrange(is.na(pfr_id) | pfr_id == "") |>
    dplyr::distinct(gsis_id, .keep_all = TRUE) |>
    dplyr::select(gsis_id, pfr_id, full_name) |>
    dplyr::mutate(norm = name_norm(full_name))

  # Merge gsis into PFR table by pfr_id
  pfr_agg <- pfr_agg |>
    dplyr::left_join(ros |> dplyr::select(pfr_id, gsis_id), by = "pfr_id") |>
    dplyr::mutate(norm = name_norm(player))

  # PBP table: rename for clarity
  pbp_all <- pbp_all |>
    dplyr::rename(gsis_id = player_id) |>
    dplyr::mutate(norm = name_norm(player_name))

  # Join PBP <-> PFR by gsis_id; for PFR rows missing gsis, try name match.
  joined <- pfr_agg |>
    dplyr::left_join(pbp_all |>
                       dplyr::select(gsis_id, pds_pg, ints_pg, games_w_pbp = games_w),
                     by = "gsis_id")

  # For rows where games_w_pbp is NA (no gsis), fall back to name match.
  fallback <- pbp_all |>
    dplyr::select(norm, pds_pg, ints_pg, games_w_pbp = games_w)
  no_pbp_idx <- which(is.na(joined$pds_pg))
  if (length(no_pbp_idx) > 0) {
    matched <- joined[no_pbp_idx, ] |>
      dplyr::select(-pds_pg, -ints_pg, -games_w_pbp) |>
      dplyr::left_join(fallback, by = "norm")
    joined[no_pbp_idx, c("pds_pg", "ints_pg", "games_w_pbp")] <-
      matched[, c("pds_pg", "ints_pg", "games_w_pbp")]
  }

  # Qualification thresholds.
  joined <- joined |>
    dplyr::mutate(
      qualifying = tgt_w >= 30 & games_w >= 8  # ~ at least half a season of PFR data
    )

  qual <- joined |> dplyr::filter(qualifying)
  message("[cb_quality] qualifying CBs: ", nrow(qual))

  # PFR sub-components (percentile-rank, then weighted).
  # Lower passer rating / cmp% allowed = better; higher (INT+PD)/tgt = better.
  # Use PDs from PBP; PFR doesn't have PDs directly (only INTs).
  qual <- qual |>
    dplyr::mutate(
      # PDs/target from PBP — convert pds_pg to per-tgt by scaling by games/(tgt/g)
      pds_per_tgt_proxy = ifelse(tgt_w > 0,
                                 (pds_w_per_yr_proxy <- 0) +
                                   (pds_pg * games_w) / pmax(tgt_w, 1),
                                 0),
      pds_per_tgt_proxy = ifelse(is.na(pds_per_tgt_proxy), 0, pds_per_tgt_proxy),
      int_pd_per_tgt    = ints_per_tgt + pds_per_tgt_proxy,
      pfr_rating_inv    = -passer_rating_allowed,
      pfr_cmppct_inv    = -cmp_pct_allowed,
      pfr_makeplays     = int_pd_per_tgt
    )

  pct <- function(x) {
    r <- rank(x, na.last = "keep", ties.method = "average")
    100 * (r - 1) / (sum(!is.na(x)) - 1)
  }

  qual <- qual |>
    dplyr::mutate(
      pfr_rating_score = pct(pfr_rating_inv),
      pfr_cmppct_score = pct(pfr_cmppct_inv),
      pfr_make_score   = pct(pfr_makeplays),
      pfr_composite    = 0.40/0.80 * pfr_rating_score + 0.25/0.80 * pfr_cmppct_score +
                         0.15/0.80 * pfr_make_score,
      pbp_composite_raw = 0.60 * pds_pg + 0.40 * ints_pg,
      pbp_composite     = pct(pbp_composite_raw),
      final_raw        = 0.80 * pfr_composite + 0.20 * pbp_composite,
      quality_score    = pct(final_raw)
    )

  # Build output table: include non-qualifying with NA score
  out <- joined |>
    dplyr::select(pfr_id, gsis_id, player, qualifying, tgt_w, games_w,
                  passer_rating_allowed, cmp_pct_allowed) |>
    dplyr::distinct(pfr_id, .keep_all = TRUE) |>
    dplyr::left_join(
      qual |>
        dplyr::distinct(pfr_id, .keep_all = TRUE) |>
        dplyr::select(pfr_id, pfr_composite, pbp_composite, quality_score),
      by = "pfr_id"
    ) |>
    dplyr::rename(player_name = player) |>
    dplyr::mutate(norm = name_norm(player_name))

  message("[cb_quality] output rows: ", nrow(out), "  scored: ",
          sum(!is.na(out$quality_score)))
  out
}

# Common first-name aliases for short<->long forms
NAME_ALIASES <- list(
  "pat" = "patrick",
  "patrick" = "pat",
  "alex" = "alexander",
  "alexander" = "alex",
  "chris" = "christopher",
  "christopher" = "chris",
  "mike" = "michael",
  "michael" = "mike",
  "tony" = "anthony",
  "anthony" = "tony",
  "matt" = "matthew",
  "matthew" = "matt",
  "nick" = "nicholas",
  "nicholas" = "nick",
  "joey" = "joseph",
  "joseph" = "joey",
  "joe" = "joseph",
  "danny" = "daniel",
  "dan" = "daniel",
  "daniel" = "dan",
  "tj" = "t j",
  "t j" = "tj",
  "aj" = "a j",
  "a j" = "aj",
  "dj" = "d j",
  "d j" = "dj",
  "jd" = "j d",
  "j d" = "jd",
  "kj" = "k j",
  "k j" = "kj"
)

candidate_norms <- function(nm) {
  base <- name_norm(nm)
  parts <- strsplit(base, " ")[[1]]
  if (length(parts) < 2) return(unique(c(base)))
  out <- c(base)
  first <- parts[1]
  rest  <- paste(parts[-1], collapse = " ")
  alias <- NAME_ALIASES[[first]]
  if (!is.null(alias)) {
    out <- c(out, paste(alias, rest))
  }
  # last-name only
  out <- c(out, parts[length(parts)])
  unique(out)
}

# Public lookup helper used by cb_wr_matchup.R
cb_score_for <- function(name, qual_df, default = 50) {
  out <- numeric(length(name))
  matched <- logical(length(name))
  for (i in seq_along(name)) {
    cands <- candidate_norms(name[i])
    hits <- qual_df[qual_df$norm %in% cands[1:min(length(cands), 2)] & !is.na(qual_df$quality_score), , drop = FALSE]
    # If still no hit, try last-name suffix match (e.g. "patrick surtain" vs "patrick surtain ii")
    if (nrow(hits) == 0) {
      last <- cands[length(cands)]
      hits <- qual_df[grepl(paste0("(^| )", last, "( |$)"), qual_df$norm) & !is.na(qual_df$quality_score), , drop = FALSE]
      # And require initial of first name to match
      if (nrow(hits) > 0) {
        first_init <- substr(cands[1], 1, 1)
        hits <- hits[substr(hits$norm, 1, 1) == first_init, , drop = FALSE]
      }
    }
    if (nrow(hits) > 0) {
      hits <- hits[order(-hits$tgt_w), ]
      out[i] <- hits$quality_score[1]
      matched[i] <- TRUE
    } else {
      out[i] <- default
      matched[i] <- FALSE
    }
  }
  list(score = round(out, 1), matched = matched)
}

if (!exists("CB_QUALITY_NO_RUN") && sys.nframe() == 0) {
  q <- build_cb_quality()
  # Print top-25 highest-rated
  top <- q[order(-q$quality_score), c("player_name", "pfr_id", "quality_score",
                                       "tgt_w", "passer_rating_allowed", "cmp_pct_allowed")] |>
         head(25)
  print(top)
}
