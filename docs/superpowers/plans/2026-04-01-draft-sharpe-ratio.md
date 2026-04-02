# NFL Draft Quasi-Sharpe Ratio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an all-R analysis that computes a quasi-Sharpe ratio for NFL draft picks by position and draft tier, producing a rendered markdown report with charts, tables, and exportable artifacts for video content.

**Architecture:** Two R scripts — a data pipeline (`data_pipeline.R`) that pulls nflreadr data, joins/cleans/computes, and exports a parquet file; and an R Markdown report (`analysis.Rmd`) that consumes the parquet and renders sections with ggplot2 charts, gt tables, and narrative. All outputs (PNGs, CSVs, rendered markdown) land in `output/`.

**Tech Stack:** R, nflreadr, tidyverse, gt, arrow, ggridges, scales

---

## File Structure

```
analysis/draft_sharpe/
├── data_pipeline.R          # Pulls nflreadr data, joins, computes, exports parquet
├── analysis.Rmd             # R Markdown report — charts, tables, narrative
├── data/
│   └── draft_sharpe_analysis.parquet  # Pipeline output (gitignored)
└── output/                  # Rendered report + artifacts (gitignored)
    ├── analysis.md
    ├── charts/              # Standalone PNGs
    ├── sharpe_ratios.csv
    ├── hit_rates.csv
    ├── player_lookup.csv
    └── fa_replacement.csv
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `analysis/draft_sharpe/data_pipeline.R`
- Create: `analysis/draft_sharpe/analysis.Rmd`
- Create: `analysis/draft_sharpe/.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p analysis/draft_sharpe/data
mkdir -p analysis/draft_sharpe/output/charts
```

- [ ] **Step 2: Create .gitignore for data and output artifacts**

Create `analysis/draft_sharpe/.gitignore`:

```
data/
output/
```

- [ ] **Step 3: Create skeleton data_pipeline.R**

Create `analysis/draft_sharpe/data_pipeline.R`:

```r
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
```

- [ ] **Step 4: Create skeleton analysis.Rmd**

Create `analysis/draft_sharpe/analysis.Rmd`:

```rmd
---
title: "NFL Draft Quasi-Sharpe Ratio Analysis"
output:
  github_document:
    html_preview: false
---

```{r setup, include=FALSE}
knitr::opts_chunk$set(
  echo = FALSE, warning = FALSE, message = FALSE,
  fig.width = 10, fig.height = 7, dpi = 300,
  fig.path = "output/charts/"
)
library(tidyverse)
library(arrow)
library(gt)
library(scales)
library(ggridges)
```

```{r load-data}
df <- read_parquet("data/draft_sharpe_analysis.parquet")
```

<!-- Report sections will be added in subsequent tasks. -->
```

- [ ] **Step 5: Verify R dependencies are available**

```bash
Rscript -e 'needed <- c("nflreadr","tidyverse","arrow","gt","scales","ggridges"); missing <- needed[!sapply(needed, requireNamespace, quietly=TRUE)]; if(length(missing)) cat("Install:", paste(missing, collapse=", "), "\n") else cat("All packages available\n")'
```

If any are missing, install:

```bash
Rscript -e 'install.packages(c("nflreadr","tidyverse","arrow","gt","scales","ggridges"), repos="https://cloud.r-project.org")'
```

- [ ] **Step 6: Commit**

```bash
git add analysis/draft_sharpe/
git commit -m "feat: scaffold draft Sharpe ratio analysis project"
```

---

### Task 2: Data Pipeline — Load and Clean Draft Picks

**Files:**
- Modify: `analysis/draft_sharpe/data_pipeline.R`

- [ ] **Step 1: Add draft picks loading and cleaning**

Append to `data_pipeline.R` after the constants section:

```r
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
```

- [ ] **Step 2: Run pipeline to verify draft loading works**

```bash
cd analysis/draft_sharpe && Rscript data_pipeline.R
```

Expected: prints count of draft picks and position groups without error.

- [ ] **Step 3: Commit**

```bash
git add analysis/draft_sharpe/data_pipeline.R
git commit -m "feat: load and clean draft picks with position mapping and tiers"
```

---

### Task 3: Data Pipeline — Load and Aggregate Snap Counts

**Files:**
- Modify: `analysis/draft_sharpe/data_pipeline.R`

- [ ] **Step 1: Add snap count loading and aggregation**

Append to `data_pipeline.R`:

```r
# --- 2. Snap Counts (first 4 seasons) ----------------------------------------

cat("Loading snap counts (2012+)...\n")
snaps_raw <- load_snap_counts(seasons = TRUE)

cat(sprintf("  Snap count seasons available: %d-%d\n",
            min(snaps_raw$season), max(snaps_raw$season)))

# For each drafted player, compute avg snap % over first 4 NFL seasons.
# Offensive players use offense_pct, defensive players use defense_pct.
snap_min_season <- min(snaps_raw$season)

# Only consider players drafted early enough to have snap data
draft_with_snap_window <- draft |>
  filter(season >= snap_min_season - ROOKIE_DEAL_YEARS + 1) |>
  mutate(
    snap_start = season,
    snap_end = season + ROOKIE_DEAL_YEARS - 1
  )

# Determine which snap column to use based on side of ball
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
```

- [ ] **Step 2: Run pipeline to verify snap aggregation**

```bash
cd analysis/draft_sharpe && Rscript data_pipeline.R
```

Expected: prints available season range and number of players with snap data.

- [ ] **Step 3: Commit**

```bash
git add analysis/draft_sharpe/data_pipeline.R
git commit -m "feat: aggregate snap counts over first 4 seasons per drafted player"
```

---

### Task 4: Data Pipeline — Hit Classification

**Files:**
- Modify: `analysis/draft_sharpe/data_pipeline.R`

- [ ] **Step 1: Join snaps to draft picks and classify hits**

Append to `data_pipeline.R`:

```r
# --- 3. Hit Classification ----------------------------------------------------

cat("Classifying hits...\n")

draft_snaps <- draft_with_snap_window |>
  left_join(snaps_agg, by = "pfr_player_id") |>
  left_join(HIT_THRESHOLDS, by = "pos_group") |>
  mutate(
    # Players with no snap data who were drafted in the snap era are busts
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
```

- [ ] **Step 2: Run pipeline to verify hit classification**

```bash
cd analysis/draft_sharpe && Rscript data_pipeline.R
```

Expected: prints hit rate summary table by position. QB/OL should be higher, RB should be lower.

- [ ] **Step 3: Commit**

```bash
git add analysis/draft_sharpe/data_pipeline.R
git commit -m "feat: classify draft picks as hit/bust using PFF snap thresholds"
```

---

### Task 5: Data Pipeline — Second Contracts and FA Replacement Cost

**Files:**
- Modify: `analysis/draft_sharpe/data_pipeline.R`

- [ ] **Step 1: Load contracts and identify second contracts**

Append to `data_pipeline.R`:

```r
# --- 4. Contracts -------------------------------------------------------------

cat("Loading contracts...\n")
contracts_raw <- load_contracts()

# Map contract positions to our position groups
contracts <- contracts_raw |>
  mutate(pos_group = POSITION_MAP[position]) |>
  filter(!is.na(pos_group), !is.na(apy_cap_pct))

cat(sprintf("  %d contracts loaded\n", nrow(contracts)))

# --- 5. Second Contracts (post-rookie deal) -----------------------------------

cat("Matching second contracts to drafted players...\n")

# For each drafted player, find their first contract signed after the rookie window.
# Rookie deals are 4 years for rounds 1, and 4 years for all others.
# We look for contracts signed in year 4-6 post-draft as the "second contract."

second_contracts <- draft_snaps |>
  select(pfr_player_id, pfr_player_name, season, pos_group) |>
  inner_join(
    contracts |> select(player, otc_id, year_signed, apy_cap_pct, apy, value, years, pos_group),
    by = "pos_group",
    relationship = "many-to-many"
  ) |>
  # Match by name (contracts use player name, draft picks use pfr_player_name)
  filter(
    str_to_lower(str_trim(pfr_player_name)) == str_to_lower(str_trim(player)),
    year_signed >= season + ROOKIE_DEAL_YEARS,
    year_signed <= season + ROOKIE_DEAL_YEARS + 2
  ) |>
  # Take the first post-rookie contract per player
  group_by(pfr_player_id) |>
  slice_min(year_signed, n = 1, with_ties = FALSE) |>
  ungroup() |>
  select(pfr_player_id, second_apy_cap_pct = apy_cap_pct,
         second_contract_year = year_signed, second_contract_apy = apy,
         second_contract_value = value, second_contract_years = years)

cat(sprintf("  Matched %d second contracts\n", nrow(second_contracts)))

# --- 6. Free Agency Replacement Cost ------------------------------------------

cat("Computing FA replacement cost by position...\n")

# FA replacement = median apy_cap_pct for non-rookie contracts by position.
# Exclude very small contracts (practice squad, etc.) by filtering apy_cap_pct > 0.1%
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
```

- [ ] **Step 2: Run pipeline to verify contract matching and FA costs**

```bash
cd analysis/draft_sharpe && Rscript data_pipeline.R
```

Expected: prints number of matched second contracts and FA replacement costs per position. QB should have highest FA cost, RB among lowest.

- [ ] **Step 3: Commit**

```bash
git add analysis/draft_sharpe/data_pipeline.R
git commit -m "feat: match second contracts and compute FA replacement cost by position"
```

---

### Task 6: Data Pipeline — Final Join and Sharpe Ratio Computation

**Files:**
- Modify: `analysis/draft_sharpe/data_pipeline.R`

- [ ] **Step 1: Join everything and compute Sharpe ratios**

Append to `data_pipeline.R`:

```r
# --- 7. Final Join ------------------------------------------------------------

cat("Building final analysis dataset...\n")

analysis_df <- draft_snaps |>
  left_join(second_contracts, by = "pfr_player_id") |>
  left_join(fa_replacement, by = "pos_group") |>
  mutate(
    # Players without second contracts get 0 (busts / out of league)
    second_apy_cap_pct = replace_na(second_apy_cap_pct, 0)
  )

cat(sprintf("  Final dataset: %d players\n", nrow(analysis_df)))

# --- 8. Sharpe Ratio Computation ----------------------------------------------

cat("Computing Sharpe ratios...\n")

# Linear Sharpe: E[return] = mean second_apy_cap_pct for the tier-position bucket
# Elite threshold: top-10 percentile of second_apy_cap_pct among ALL players
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
    # Linear Sharpe: (mean return - risk-free) / volatility
    sharpe_linear = (mean_second_contract - fa_replacement) / sd_second_contract,
    # Elite-weighted Sharpe: (elite probability - baseline elite prob) / volatility
    # Scale elite_prob by the elite threshold value to put it in same units
    sharpe_elite = (elite_prob * elite_threshold - fa_replacement) / sd_second_contract
  ) |>
  # Replace NaN/Inf from zero-variance buckets

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

# Also export summary tables as CSV for easy access
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
```

- [ ] **Step 2: Run the full pipeline end to end**

```bash
cd analysis/draft_sharpe && Rscript data_pipeline.R
```

Expected: completes without error, prints summary tables, creates parquet and CSV files.

- [ ] **Step 3: Spot-check outputs**

```bash
cd analysis/draft_sharpe && Rscript -e 'library(arrow); df <- read_parquet("data/draft_sharpe_analysis.parquet"); cat("Rows:", nrow(df), "\nCols:", ncol(df), "\n"); print(head(df, 5))'
```

- [ ] **Step 4: Commit**

```bash
git add analysis/draft_sharpe/data_pipeline.R
git commit -m "feat: compute Sharpe ratios and export analysis dataset"
```

---

### Task 7: R Markdown Report — Setup, Hit Rates, and Nonlinearity Sections

**Files:**
- Modify: `analysis/draft_sharpe/analysis.Rmd`

- [ ] **Step 1: Write the Setup, Hit Rates, and Nonlinearity sections**

Replace the contents of `analysis/draft_sharpe/analysis.Rmd` with:

````rmd
---
title: "NFL Draft Quasi-Sharpe Ratio Analysis"
subtitle: "How much is a draft pick really worth, by position?"
output:
  github_document:
    html_preview: false
---

```{r setup, include=FALSE}
knitr::opts_chunk$set(
  echo = FALSE, warning = FALSE, message = FALSE,
  fig.width = 10, fig.height = 7, dpi = 300,
  fig.path = "output/charts/"
)
library(tidyverse)
library(arrow)
library(gt)
library(scales)
library(ggridges)

# Color palette for positions
pos_colors <- c(
  "QB" = "#E41A1C", "RB" = "#377EB8", "WR" = "#4DAF4A", "TE" = "#984EA3",
  "OT" = "#FF7F00", "IOL" = "#FFFF33", "EDGE" = "#A65628", "DL" = "#F781BF",
  "LB" = "#999999", "CB" = "#66C2A5", "S" = "#FC8D62"
)

tier_order <- c("Top 10", "Late 1st", "Day 2", "Day 3 Early", "Day 3 Late")
```

```{r load-data}
df <- read_parquet("data/draft_sharpe_analysis.parquet")
sharpe <- read_csv("output/sharpe_ratios.csv", show_col_types = FALSE)
fa_costs <- read_csv("output/fa_replacement.csv", show_col_types = FALSE)

df <- df |> mutate(tier = factor(tier, levels = tier_order))
sharpe <- sharpe |> mutate(tier = factor(tier, levels = tier_order))
```

## The Setup

A **quasi-Sharpe Ratio** for NFL draft picks. The classic Sharpe Ratio measures excess return per unit of risk. We apply the same logic to the draft:

$$\text{Quasi-Sharpe} = \frac{\text{Expected Return} - \text{Risk-Free Rate}}{\text{Volatility}}$$

| Component | What it measures |
|---|---|
| **Expected Return** | Hit rate × average second-contract value (as % of salary cap) |
| **Risk-Free Rate** | Median free-agent contract for that position (what you'd pay without using a pick) |
| **Volatility** | Standard deviation of second-contract outcomes (including busts at $0) |

A high ratio means: reliable surplus value above free agency. A low ratio means: you're gambling.

**Hit definition** follows PFF's methodology: a player is a "hit" if their average snap percentage over their first 4 NFL seasons reaches at least 2/3 of the positional baseline for a full-time starter.

**Nonlinearity insight** from Brill & Wyner (2024): not all hits are equal. We compute the ratio two ways — linear (expected value) and elite-weighted (right-tail probability) — to show how the story changes when you account for the outsized value of elite outcomes.

---

## Hit Rates by Position × Tier

```{r hit-rates-heatmap, fig.width=10, fig.height=7}
hit_rates <- df |>
  group_by(pos_group, tier) |>
  summarise(n = n(), hit_rate = mean(is_hit), .groups = "drop")

ggplot(hit_rates, aes(x = tier, y = reorder(pos_group, hit_rate), fill = hit_rate)) +
  geom_tile(color = "white", linewidth = 0.5) +
  geom_text(aes(label = sprintf("%.0f%%\n(n=%d)", hit_rate * 100, n)),
            size = 3.5, color = "white", fontface = "bold") +
  scale_fill_gradient2(low = "#c62828", mid = "#ff8f00", high = "#2e7d32",
                       midpoint = 0.4, labels = percent,
                       name = "Hit Rate") +
  labs(title = "Draft Hit Rates by Position and Tier",
       subtitle = "Hit = avg snap % over first 4 seasons ≥ 2/3 of positional baseline",
       x = NULL, y = NULL) +
  theme_minimal(base_size = 14) +
  theme(
    panel.grid = element_blank(),
    axis.text.x = element_text(angle = 0, hjust = 0.5),
    plot.title = element_text(face = "bold")
  )
```

```{r hit-rates-table}
hit_rates |>
  pivot_wider(names_from = tier, values_from = c(hit_rate, n)) |>
  gt() |>
  fmt_percent(starts_with("hit_rate_"), decimals = 0) |>
  tab_header(title = "Hit Rates: Position × Draft Tier")
```

---

## The Nonlinearity Story

Not all hits are created equal. A "hit" QB commands 10%+ of the salary cap on their second deal. A "hit" RB might get 3%. The distributions tell the real story.

```{r nonlinearity-ridgeline, fig.width=10, fig.height=8}
# Filter to players with any second contract data for visualization
df_with_contracts <- df |>
  filter(second_apy_cap_pct > 0)

ggplot(df_with_contracts, aes(x = second_apy_cap_pct, y = reorder(pos_group, second_apy_cap_pct, FUN = median), fill = pos_group)) +
  geom_density_ridges(alpha = 0.7, scale = 1.5, quantile_lines = TRUE, quantiles = c(0.5, 0.9)) +
  scale_x_continuous(labels = percent_format(accuracy = 0.1), limits = c(0, NA)) +
  scale_fill_manual(values = pos_colors, guide = "none") +
  labs(title = "Second Contract Value Distribution by Position",
       subtitle = "Lines show median (50th) and elite threshold (90th percentile) | Among players who earned a second contract",
       x = "Second Contract APY (% of Salary Cap)",
       y = NULL) +
  theme_minimal(base_size = 14) +
  theme(plot.title = element_text(face = "bold"))
```

```{r elite-probability, fig.width=10, fig.height=6}
elite_threshold <- quantile(df$second_apy_cap_pct[df$second_apy_cap_pct > 0], 0.90, na.rm = TRUE)

elite_by_tier <- df |>
  group_by(pos_group, tier) |>
  summarise(elite_prob = mean(second_apy_cap_pct >= elite_threshold), .groups = "drop")

ggplot(elite_by_tier |> filter(pos_group %in% c("QB", "RB", "WR", "TE", "EDGE", "OT")),
       aes(x = tier, y = elite_prob, color = pos_group, group = pos_group)) +
  geom_line(linewidth = 1.2) +
  geom_point(size = 3) +
  scale_y_continuous(labels = percent) +
  scale_color_manual(values = pos_colors) +
  labs(title = "Probability of an Elite Outcome by Position and Tier",
       subtitle = sprintf("Elite = second contract ≥ %.2f%% of cap (90th percentile)", elite_threshold * 100),
       x = NULL, y = "P(Elite)", color = "Position") +
  theme_minimal(base_size = 14) +
  theme(plot.title = element_text(face = "bold"))
```
````

- [ ] **Step 2: Render to verify first sections work**

```bash
cd analysis/draft_sharpe && Rscript -e 'rmarkdown::render("analysis.Rmd", output_file = "output/analysis.md")'
```

Expected: renders without error, produces `output/analysis.md` and PNGs in `output/charts/`.

- [ ] **Step 3: Commit**

```bash
git add analysis/draft_sharpe/analysis.Rmd
git commit -m "feat: add hit rate and nonlinearity sections to report"
```

---

### Task 8: R Markdown Report — FA Replacement, Sharpe Ratio, and Curves Sections

**Files:**
- Modify: `analysis/draft_sharpe/analysis.Rmd`

- [ ] **Step 1: Append FA Replacement Cost, Sharpe Ratio, and Curves sections**

Add the following sections to `analysis.Rmd` after the nonlinearity section:

````rmd

---

## Free Agency Replacement Cost

The "risk-free rate" — what it costs to acquire each position without spending a draft pick.

```{r fa-replacement, fig.width=10, fig.height=6}
ggplot(fa_costs, aes(x = reorder(pos_group, fa_median_apy_cap_pct), y = fa_median_apy_cap_pct, fill = pos_group)) +
  geom_col(alpha = 0.85) +
  geom_text(aes(label = sprintf("%.2f%%", fa_median_apy_cap_pct * 100)),
            hjust = -0.1, size = 4, fontface = "bold") +
  scale_y_continuous(labels = percent_format(accuracy = 0.1), expand = expansion(mult = c(0, 0.15))) +
  scale_fill_manual(values = pos_colors, guide = "none") +
  coord_flip() +
  labs(title = "Free Agency Replacement Cost by Position",
       subtitle = "Median APY as % of salary cap for non-rookie contracts",
       x = NULL, y = "Median APY (% of Cap)") +
  theme_minimal(base_size = 14) +
  theme(plot.title = element_text(face = "bold"))
```

---

## The Sharpe Ratio

The money shot. Higher = more efficient use of a draft pick at that position and tier.

```{r sharpe-heatmap, fig.width=10, fig.height=7}
ggplot(sharpe, aes(x = tier, y = reorder(pos_group, sharpe_linear, FUN = function(x) mean(x, na.rm = TRUE)),
                   fill = sharpe_linear)) +
  geom_tile(color = "white", linewidth = 0.5) +
  geom_text(aes(label = sprintf("%.2f", sharpe_linear)),
            size = 3.5, color = "white", fontface = "bold") +
  scale_fill_gradient2(low = "#c62828", mid = "#fff9c4", high = "#2e7d32",
                       midpoint = 0, name = "Sharpe\nRatio") +
  labs(title = "Quasi-Sharpe Ratio by Position and Draft Tier",
       subtitle = "(Expected Return − FA Replacement Cost) / Volatility",
       x = NULL, y = NULL) +
  theme_minimal(base_size = 14) +
  theme(
    panel.grid = element_blank(),
    plot.title = element_text(face = "bold")
  )
```

```{r sharpe-table}
sharpe |>
  select(pos_group, tier, n, hit_rate, mean_second_contract, fa_replacement, sd_second_contract, sharpe_linear, sharpe_elite) |>
  arrange(desc(sharpe_linear)) |>
  gt() |>
  fmt_percent(c(hit_rate), decimals = 0) |>
  fmt_number(c(mean_second_contract, fa_replacement, sd_second_contract, sharpe_linear, sharpe_elite), decimals = 3) |>
  tab_header(title = "Quasi-Sharpe Ratio — Full Breakdown")
```

---

## Sharpe Ratio Curves

How does the value of each position degrade across the draft?

```{r sharpe-curves, fig.width=10, fig.height=7}
ggplot(sharpe |> filter(!is.na(sharpe_linear)),
       aes(x = tier, y = sharpe_linear, color = pos_group, group = pos_group)) +
  geom_line(linewidth = 1.2) +
  geom_point(size = 3) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray40") +
  scale_color_manual(values = pos_colors) +
  labs(title = "Quasi-Sharpe Ratio Across Draft Tiers",
       subtitle = "Below zero = negative expected value vs. free agency",
       x = NULL, y = "Sharpe Ratio", color = "Position") +
  theme_minimal(base_size = 14) +
  theme(plot.title = element_text(face = "bold"))
```
````

- [ ] **Step 2: Render to verify**

```bash
cd analysis/draft_sharpe && Rscript -e 'rmarkdown::render("analysis.Rmd", output_file = "output/analysis.md")'
```

- [ ] **Step 3: Commit**

```bash
git add analysis/draft_sharpe/analysis.Rmd
git commit -m "feat: add FA replacement, Sharpe heatmap, and curve sections to report"
```

---

### Task 9: R Markdown Report — Linear vs Elite-Weighted and Player Lookup

**Files:**
- Modify: `analysis/draft_sharpe/analysis.Rmd`

- [ ] **Step 1: Append Linear vs Elite-Weighted and Player Lookup sections**

Add the following to `analysis.Rmd`:

````rmd

---

## Linear vs Elite-Weighted

The same ratio, two lenses. Linear uses expected value. Elite-weighted asks: "what's the probability of a star?"

```{r linear-vs-elite, fig.width=12, fig.height=6}
sharpe_long <- sharpe |>
  filter(!is.na(sharpe_linear), !is.na(sharpe_elite)) |>
  select(pos_group, tier, sharpe_linear, sharpe_elite) |>
  pivot_longer(cols = c(sharpe_linear, sharpe_elite),
               names_to = "method", values_to = "ratio") |>
  mutate(method = if_else(method == "sharpe_linear", "Linear (Expected Value)", "Elite-Weighted (Right Tail)"))

ggplot(sharpe_long |> filter(pos_group %in% c("QB", "RB", "WR", "TE", "EDGE", "OT")),
       aes(x = tier, y = ratio, color = pos_group, group = pos_group)) +
  geom_line(linewidth = 1.1) +
  geom_point(size = 2.5) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray40") +
  facet_wrap(~ method) +
  scale_color_manual(values = pos_colors) +
  labs(title = "Linear vs Elite-Weighted Sharpe Ratio",
       subtitle = "How the story changes when you weight for superstar upside",
       x = NULL, y = "Sharpe Ratio", color = "Position") +
  theme_minimal(base_size = 13) +
  theme(
    plot.title = element_text(face = "bold"),
    strip.text = element_text(face = "bold", size = 13)
  )
```

---

## Player Lookup

Recent draft picks with their positional Sharpe context. Where did they land in the distribution?

```{r player-lookup}
player_lookup <- read_csv("output/player_lookup.csv", show_col_types = FALSE)

# Show last 5 draft classes for the table
player_lookup |>
  filter(season >= max(season) - 4) |>
  mutate(
    pctl = percent_rank(second_apy_cap_pct),
    outcome = case_when(
      is_hit ~ "Hit",
      TRUE ~ "Bust"
    )
  ) |>
  select(Player = pfr_player_name, Pos = pos_group, Year = season, Pick = pick,
         Tier = tier, Outcome = outcome, `Snap %` = avg_snap_pct,
         `2nd Contract (Cap %)` = second_apy_cap_pct,
         `Sharpe (Linear)` = sharpe_linear, `Sharpe (Elite)` = sharpe_elite) |>
  gt() |>
  fmt_percent(c(`Snap %`, `2nd Contract (Cap %)`), decimals = 1) |>
  fmt_number(c(`Sharpe (Linear)`, `Sharpe (Elite)`), decimals = 2) |>
  tab_header(
    title = "Player Lookup — Recent Draft Picks",
    subtitle = "Sharpe ratio reflects the historical profile for that position × tier"
  )
```

---

## Key Takeaways

```{r takeaways, results='asis'}
# Generate per-position one-liners based on the data
best_pos <- sharpe |>
  filter(tier == "Top 10", !is.na(sharpe_linear)) |>
  slice_max(sharpe_linear, n = 1)

worst_pos <- sharpe |>
  filter(tier == "Top 10", !is.na(sharpe_linear)) |>
  slice_min(sharpe_linear, n = 1)

cat(sprintf("- **Best top-10 value:** %s (Sharpe = %.2f) — highest surplus above FA replacement with lowest variance\n",
            best_pos$pos_group, best_pos$sharpe_linear))
cat(sprintf("- **Worst top-10 value:** %s (Sharpe = %.2f) — the draft pick premium over free agency doesn't justify the bust risk\n",
            worst_pos$pos_group, worst_pos$sharpe_linear))

# Elite shift
elite_biggest_gainer <- sharpe |>
  filter(!is.na(sharpe_linear), !is.na(sharpe_elite)) |>
  mutate(elite_shift = sharpe_elite - sharpe_linear) |>
  slice_max(elite_shift, n = 1)

cat(sprintf("- **Biggest elite-weight gainer:** %s in %s — the nonlinear upside shifts the calculus significantly\n",
            elite_biggest_gainer$pos_group, elite_biggest_gainer$tier))
cat("- **The nonlinearity matters:** positions with fat right tails (QB, EDGE) look much better when you weight for elite outcomes vs. expected value\n")
cat("- **Free agency is the baseline:** cheap-to-replace positions (RB) need dramatically higher hit rates to justify early picks\n")
```
````

- [ ] **Step 2: Final render of complete report**

```bash
cd analysis/draft_sharpe && Rscript -e 'rmarkdown::render("analysis.Rmd", output_file = "output/analysis.md")'
```

Expected: full report renders with all 9 sections, charts in `output/charts/`, and the rendered markdown at `output/analysis.md`.

- [ ] **Step 3: Verify all output artifacts exist**

```bash
ls -la analysis/draft_sharpe/output/
ls -la analysis/draft_sharpe/output/charts/
```

Expected: `analysis.md`, CSVs, and PNG chart files all present.

- [ ] **Step 4: Commit**

```bash
git add analysis/draft_sharpe/analysis.Rmd
git commit -m "feat: add linear vs elite comparison, player lookup, and takeaways to report"
```

---

### Task 10: End-to-End Run and Polish

**Files:**
- Possibly modify: `analysis/draft_sharpe/data_pipeline.R`, `analysis/draft_sharpe/analysis.Rmd`

- [ ] **Step 1: Clean run from scratch**

```bash
cd analysis/draft_sharpe
rm -rf data/ output/
mkdir -p data output/charts
Rscript data_pipeline.R
Rscript -e 'rmarkdown::render("analysis.Rmd", output_file = "output/analysis.md")'
```

Expected: full pipeline + report runs clean from empty state.

- [ ] **Step 2: Review rendered markdown for story coherence**

Open `analysis/draft_sharpe/output/analysis.md` and verify:
- All charts rendered (no broken image links)
- Tables are populated with reasonable numbers
- Sharpe ratios make directional sense (QB/OT top-10 should be high, RB should be low)
- Narrative takeaways auto-generated correctly

- [ ] **Step 3: Fix any issues found in review**

Address any chart formatting, data quality, or narrative issues.

- [ ] **Step 4: Final commit**

```bash
git add analysis/draft_sharpe/
git commit -m "feat: complete NFL Draft Quasi-Sharpe Ratio analysis"
```
