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
  "T" = "OT", "OT" = "OT",
  "G" = "IOL", "C" = "IOL", "OL" = "IOL", "OG" = "IOL",
  "DE" = "EDGE", "OLB" = "EDGE", "EDGE" = "EDGE",
  "DT" = "DL", "NT" = "DL", "DL" = "DL",
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

# Pipeline steps will be added in subsequent tasks.
