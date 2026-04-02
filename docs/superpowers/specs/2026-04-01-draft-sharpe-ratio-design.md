# NFL Draft Quasi-Sharpe Ratio Analysis

**Date:** 2026-04-01
**Purpose:** Standalone R analysis for video content. Produces a rendered markdown report with charts, tables, and exportable artifacts a video content creator can use to tell the story of positional value in the NFL draft.

## Core Concept

A quasi-Sharpe Ratio applied to NFL draft picks by position and draft tier. The ratio answers: **"How much excess value does drafting this position at this slot generate above what you could acquire via free agency, relative to how volatile the outcomes are?"**

**Formula:**

```
Quasi-Sharpe Ratio = (Expected Return - Risk-Free Rate) / Volatility
```

| Component | Definition | Data Source |
|---|---|---|
| **Expected Return** | Hit rate x avg second-contract `apy_cap_pct` for hits, by position x tier. Computed two ways: linear (expected value) and elite-weighted (right-tail probability above a threshold). | `load_draft_picks()`, `load_snap_counts()`, `load_contracts()` |
| **Risk-Free Rate** | Median free-agent `apy_cap_pct` for that position — replacement-level cost without spending a draft pick. | `load_contracts()` filtered to non-rookie FA signings |
| **Volatility** | Standard deviation of second-contract `apy_cap_pct` outcomes (including busts at ~0%) for that position x tier. | Derived from joined dataset |

## Hit Rate Methodology

Follows PFF/Timo Riske's approach:

1. Calculate each player's average snap percentage over their first 4 NFL seasons using `load_snap_counts()`.
2. Establish positional baselines: average snap % of the top 32 players at each position leaguewide.
3. A player is a **"hit"** if their 4-season avg snap % reaches at least **2/3 of the positional baseline**.
4. All others are classified as **"busts"** for ratio purposes.

### Positional Baselines (from PFF)

| Position | Baseline Snap % | Hit Threshold (2/3) |
|---|---|---|
| IOL | 99.6% | 66.4% |
| OT | 97.4% | 64.9% |
| S | 95.2% | 63.5% |
| LB / CB | 92.3% | 61.5% |
| WR | 85.3% | 56.9% |
| QB | 83.0% | 55.3% |
| EDGE | 81.1% | 54.1% |
| DL | 71.7% | 47.8% |
| TE | 71.3% | 47.5% |
| RB | 56.4% | 37.6% |

## Nonlinearity (Brill & Wyner Insight)

Traditional expected-value analysis misses that elite outcomes are disproportionately valuable. Per Brill & Wyner (CMU CMSAC 2024):

- Variance in second-contract outcomes decays convexly across draft position.
- Earlier picks have fatter right tails — higher probability of elite outcomes.
- GMs implicitly value this right-tail probability, not just expected value.

We compute the ratio **two ways**:

1. **Linear (E[V]):** Expected return = hit rate x mean second-contract `apy_cap_pct` of hits.
2. **Elite-Weighted (P[elite]):** Expected return = probability that a pick produces a second contract above a defined elite threshold (e.g., top-10 at position in `apy_cap_pct`). This captures the nonlinear upside.

Presenting both side-by-side reveals how positions like QB look much better under elite-weighted analysis (fat right tail) while positions like RB degrade further (thin right tail even among hits).

## Draft Tiers

| Tier | Picks |
|---|---|
| Top 10 | 1-10 |
| Late 1st | 11-32 |
| Day 2 | 33-64 |
| Day 3 Early | 65-100 |
| Day 3 Late | 101+ |

## Position Groups

QB, RB, WR, TE, OT, IOL, EDGE, DL, LB, CB, S

PFR's `position` field from `load_draft_picks()` will need mapping to these groups (e.g., DE/OLB -> EDGE, DT/NT -> DL, G/C -> IOL, T -> OT).

## Salary Normalization

All dollar values are expressed as `apy_cap_pct` — average annual salary as a percentage of the salary cap at time of signing. This makes values comparable across eras without manual inflation adjustment. Available directly in `load_contracts()`.

## Data Pipeline

### File: `analysis/draft_sharpe/data_pipeline.R`

**Inputs (all from nflreadr):**
- `load_draft_picks(seasons = TRUE)` — all available draft picks
- `load_snap_counts(seasons = <range>)` — snap data (limiting factor on year range)
- `load_contracts()` — all contracts from OverTheCap
- `load_rosters(seasons = TRUE)` — for position mapping and player IDs

**Processing Steps:**

1. **Draft picks:** Load all picks, map positions to groups, assign draft tiers.
2. **Snap counts:** Aggregate snap % by player over first 4 NFL seasons. Join to draft picks via `gsis_id` or `pfr_player_id`.
3. **Hit classification:** Apply PFF thresholds to classify each drafted player as hit or bust.
4. **Second contracts:** Identify each player's second NFL contract from `load_contracts()`. Logic: for each drafted player, find the first non-rookie contract signed after their rookie deal window (years 4-5 post-draft). Players with no second contract get `apy_cap_pct = 0`.
5. **FA replacement cost:** From `load_contracts()`, compute median `apy_cap_pct` for free-agent signings (non-rookie, non-franchise-tag) by position group. This is the risk-free rate.
6. **Join:** Produce a single analysis-ready dataframe: one row per drafted player with draft info, snap %, hit flag, second-contract `apy_cap_pct`, and positional FA replacement cost.

**Output:** `analysis/draft_sharpe/data/draft_sharpe_analysis.parquet`

### Data Availability Constraint

Snap count data availability determines the analysis window. Draft picks go back to 1980, contracts are comprehensive, but PFR snap counts via nflreadr likely start around 2012. The pipeline should detect the actual range and document it.

## Analysis & Report

### File: `analysis/draft_sharpe/analysis.Rmd`

Renders to GitHub-flavored markdown with embedded PNG charts. Sections:

### 1. The Setup
- What is the quasi-Sharpe ratio
- Why positional value in the draft isn't what you think
- Methodology summary (hit rate definition, Sharpe formula, data sources)

### 2. Hit Rates by Position x Tier
- Heatmap: position (rows) x tier (columns), cells = hit rate %
- Table with exact values
- Narrative: which positions hit most reliably and where

### 3. The Nonlinearity Story
- Distribution plots (ridgeline or violin) of second-contract `apy_cap_pct` by position
- Highlight the right-tail fatness difference: QB vs RB vs WR
- "A top-10 QB pick has X% chance of an elite outcome; a top-10 RB pick has Y%"

### 4. Free Agency Replacement Cost
- Bar chart of median FA `apy_cap_pct` by position
- The risk-free rate visualization: "You can buy an RB for 1.5% of cap, but a QB costs 8%"

### 5. The Sharpe Ratio — The Money Shot
- Color-coded heatmap: position x tier, cell = Sharpe ratio
- Summary table with ranks
- Narrative: which position-tier combos are the best and worst bets

### 6. The Sharpe Ratio Curves
- Line chart: x-axis = tier, y-axis = Sharpe ratio, one line per position
- Shows how value degrades (or doesn't) across the draft by position

### 7. Linear vs Elite-Weighted
- Side-by-side heatmaps or overlaid curves
- Shows how the story changes when you weight for nonlinear upside
- Key callout: positions where the gap is largest (QB gets much better, RB gets worse)

### 8. Player Lookup Table
- Filterable table of draft picks (last ~10 years for relevance)
- Columns: player name, position, draft year, pick, tier, hit/bust, second-contract `apy_cap_pct`, historical Sharpe ratio for that position-tier profile, percentile rank within profile
- Highlighted example: Jeremiah Love and comparable RBs at similar draft slots

### 9. Key Takeaways
- Bullet points for video script
- The one-liner narrative for each position

## Exported Artifacts (in `analysis/draft_sharpe/output/`)

- All charts as standalone high-resolution PNGs
- `sharpe_ratios.csv` — the ratio table
- `hit_rates.csv` — hit rate table
- `player_lookup.csv` — player-level data
- `fa_replacement.csv` — free agency costs by position
- Rendered `analysis.md`

## R Libraries

- `nflreadr` — data ingestion
- `tidyverse` (`dplyr`, `tidyr`, `ggplot2`, `stringr`, `purrr`) — data wrangling and visualization
- `gt` — polished tables
- `arrow` — parquet I/O
- `scales` — axis formatting
- `ggridges` — ridgeline distribution plots (section 3)

## References

- Brill, R.S. & Wyner, A.J. (2024). "The Winner of the NFL Draft is Not Necessarily Cursed." CMU CMSAC. https://arxiv.org/html/2411.10400v1
- Riske, T. / PFF. "What Historical Hit Rates Reveal About Positional Success." https://www.pff.com/news/draft-what-historical-hit-rates-reveal-about-positional-success
- nflreadr documentation. https://nflreadr.nflverse.com/
