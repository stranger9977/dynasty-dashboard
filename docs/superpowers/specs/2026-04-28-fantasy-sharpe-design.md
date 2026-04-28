# Fantasy Dynasty Sharpe — Design Spec

**Date:** 2026-04-28
**Status:** Draft, pending user approval
**Owner:** Nick

## Summary

Recreate the NFL Draft Quasi-Sharpe methodology from `draft-sharpe-analysis` for dynasty fantasy football. Two artifacts ship together:

1. **Long-form article** (`analysis/fantasy_sharpe/analysis.Rmd` → self-contained HTML) — historical study of dynasty rookie ADP and startup ADP, indexed against fantasy production *and* asset value.
2. **Streamlit projection tool** (`views/fantasy_sharpe_projection.py`) — applies the trained methodology to the *current* rookie class, projecting per-player 4-year fantasy outcomes and KTC asset trajectories.

Both live in the `dynasty-dashboard` repo. The article explains *why* the methodology works; the tool *applies* it interactively to 2026.

## Why a fantasy Sharpe

Dynasty drafters trade off ceiling vs floor at every pick. The original NFL Sharpe answers "did the pick beat what we'd have paid an FA?" using contract value. The fantasy version answers two parallel dynasty questions:

- **Win-now teams** care about *production*: did this pick deliver fantasy points relative to a startable baseline?
- **Rebuilding teams** care about *asset value*: did this pick build tradeable KTC value relative to a startable-asset baseline?

These two Sharpes can disagree. A Tony-Pollard-archetype RB can produce well without ever ascending in KTC. A Travis-Etienne-archetype prospect can build huge KTC value off uneven production. Showing both is the dynasty-native view.

## Scope

**In:**
- Historical Sharpe analysis indexed by dynasty rookie ADP and dynasty startup ADP, both via KTC superflex value as a proxy.
- Two parallel Sharpes per cohort: Production (PPG-share) and Asset (KTC-value).
- Position-adjusted return (player PPG / positional baseline PPG, season-weighted).
- Counter-analysis style projection model for the current rookie class using NGS, NFL draft pick, and at-draft KTC value as features.
- Self-contained HTML article + Streamlit interactive view, both in `dynasty-dashboard`.

**Out:**
- Live ADP from Dynasty Data Lab or Sleeper aggregation. KTC is the proxy for v1; real ADP is a v2 follow-up.
- Trade-impact analysis, in-season redraft tools, league-specific scoring beyond standard PPR / half-PPR / std + 1QB / superflex toggles.
- Defense / kicker.

## Methodology

### Universe and tiers

Two analyses run in parallel:

- **Rookie ADP analysis** — rank rookies in their entry year by KTC superflex value at a fixed snapshot **one week post-NFL-draft** (the period when most dynasty rookie drafts run, after landing-spot uncertainty has resolved) as the rookie-pick proxy.
- **Startup ADP analysis** — rank all dynasty-relevant players at a fixed annual snapshot **August 1** (pre-season, when the bulk of dynasty startups draft) by KTC superflex value as the startup-pick proxy.

Tiers:
- Rookie: `1.01-1.04` / `1.05-1.08` / `1.09-1.12` / `R2 (2.01-2.12)` / `R3+`.
- Startup: `Top 12` / `13-36` / `37-72` / `73-150` / `151+`.

Eligibility: rookies who entered the NFL in **2020-2022 inclusive**. KTC daily history covers Y1-Y4 for those cohorts and the 4-year fantasy window is complete. Cohort sizes: roughly 45-60 fantasy-relevant rookies/year × 3 = ~150-180 player rows.

Positions: QB, RB, WR, TE only.

### Production Sharpe (win-now framing)

- **Return per player:** 4-year PPG share. Concretely:
  - **Numerator** = (total fantasy points across the player's Y1-Y4 seasons) / (4 × 17 = 68 expected games). Using expected games rather than games played means injuries and benchings naturally drag the return without needing extra logic.
  - **Denominator** = positional baseline PPG, computed per-season as the **mean PPG of the startable pool** (QB1-24 / RB1-24 / WR1-36 / TE1-12, matching superflex 12-team starting lineups), then averaged across the player's four seasons (so the baseline tracks the era a given player entered).
  - **Share** = numerator / denominator. A share of 1.0 means the player produced like a positional starter; 0.5 means half that; 1.5 means top-tier.
- **Replacement:** PPG share of QB24 / RB24 / WR36 / TE12 (superflex starting baselines for a 12-team league), measured per-season then averaged across the player's rookie window.
- **Hit:** player's PPG share ≥ 0.67 (direct port of the original 67%-of-baseline rule).
- **Risk:** sd of player return within `(position × tier)` bucket.
- **Sharpe (linear):** `(mean_return − replacement) / sd_return`.
- **Sharpe (elite):** `(elite_prob × elite_threshold − replacement) / sd_return`, where `elite_threshold` is the 90th percentile of player return.

### Asset Sharpe (rebuild framing)

- **Return per player:** **peak KTC superflex value** observed during Y1-Y4 of the player's rookie window. End-of-Y4 KTC reported as a secondary stat for reference.
- **Replacement:** KTC value of QB24 / RB24 / WR36 / TE12 in the matching season, averaged across the player's window.
- **Hit:** player's peak KTC ≥ replacement KTC × 1.0 — i.e., they at some point became a tradeable startable-tier asset.
- **Risk:** sd of peak KTC within `(position × tier)` bucket.
- **Sharpe formulas:** same shapes as Production, in KTC value units.

### Scoring formats

Default: half-PPR, superflex. Toggles: PPR / half / std and 1QB / superflex. KTC is superflex-leaning, so the asset-value side will skew toward QB premium regardless; that's expected and noted in the article.

### Counter-analysis projection model

Trained on the same 2020-2022 cohorts (so we have completed 4-year windows). Per player:

- **Features:** NGS prospect metrics (RAS, athletic measurables, college production), `log(pick)` for NFL draft pick number, KTC superflex value at one week post-NFL-draft. Mirrors `R/grader_projection.R` from the existing draft Sharpe counter-analysis.
- **Targets:** 4-year PPG share, peak KTC value (fit separately, two models).
- **Model:** **quantile regression** (`quantreg::rq`) at τ ∈ {0.10, 0.50, 0.90} per (position × target). Three quantile fits per model produce floor / median / ceiling outcomes. Quantile regression is robust to outliers and produces asymmetric intervals — important because dynasty fantasy outcomes are skewed (hard floor at 0, long upside tail). Matches the existing counter-analysis methodology.
- **Fallback:** when feature data is missing for a prospect, fall back to empirical positional quantiles of the training cohort's outcomes (same fallback strategy as the existing draft-Sharpe counter-analysis).
- **Outputs:** per-player floor/median/ceiling projections for both targets, written to `analysis/fantasy_sharpe/data/projection_model.parquet`.

The Streamlit view loads coefficients + 2026-rookie features and renders projections deterministically — no model fitting in the view.

## Repository layout

```
dynasty-dashboard/
├── analysis/
│   └── fantasy_sharpe/
│       ├── data_pipeline.R          # builds historical Sharpe + projection-model outputs
│       ├── analysis.Rmd             # the article
│       ├── analysis.html            # self-contained, committed
│       ├── data/                    # parquet artifacts (gitignored)
│       │   ├── fantasy_sharpe.parquet           # player-level historical
│       │   ├── tier_sharpe.parquet              # tier-level summary
│       │   └── projection_model.parquet         # coefficients + 2026 features + predictions
│       ├── output/                  # CSVs (gitignored)
│       └── charts/                  # PNGs (committed)
├── ingestion/
│   ├── ktc.py                       # add force-refresh flag (bypass 7-day TTL)
│   ├── ktc_history.py               # add force-refresh flag
│   └── fantasy_points_history.py    # NEW — pulls weekly fantasy points via R-side nflreadr
└── views/
    └── fantasy_sharpe_projection.py # NEW — Streamlit projection tool, reads parquet
```

The R pipeline writes a stable parquet schema; the Streamlit view depends only on that schema.

### Data inputs

- **KTC current snapshot** — `data/ktc.parquet` (already present, refreshed via `ingestion/ktc.py`).
- **KTC daily history** — `data/ktc_history/*.json` (already present, refreshed via `ingestion/ktc_history.py`). Daily values back to 2020 for ~290 covered players.
- **Fantasy points weekly** — pulled fresh via `nflreadr::load_player_stats()`. Aggregated to per-season PPG (PPR / half / std).
- **NGS / prospect** — `nflreadr::load_combine()` and equivalents for college production. Joined by gsis_id / pfr_id with KTC's `mfl_id` via `db_playerids.csv` (already used by the existing draft Sharpe pipeline).
- **NFL draft picks** — `nflreadr::load_draft_picks()` for actual draft pick number per rookie.

### Data refresh

The pipeline must run a fresh KTC pull before producing 2026 projections, since pre-NFL-draft KTC values shift hard once landing spots are known. Both `ingestion/ktc.py` and `ingestion/ktc_history.py` get a `--force` flag that bypasses the existing 7-day TTL cache.

### Data flow

```
nflreadr (fantasy points, NGS, draft picks)
KTC ingestion (refreshed post-NFL-draft)
        │
        ▼
analysis/fantasy_sharpe/data_pipeline.R
        │
        ▼
fantasy_sharpe.parquet
tier_sharpe.parquet                    ──→ analysis.Rmd ──→ analysis.html
projection_model.parquet
        │
        ▼
views/fantasy_sharpe_projection.py     (Streamlit interactive tool)
```

## Article structure (`analysis.Rmd`)

1. **Why position-adjusted PPG and KTC value, not raw fantasy points** — quick methodological framing.
2. **The historical landscape, rookie ADP** — Sharpe-by-tier × position table; headline chart (Sharpe across rookie tiers, faceted by position), both Production and Asset versions.
3. **The historical landscape, startup ADP** — same shape, different x-axis. Where startups are efficient vs inefficient.
4. **Production vs Asset divergence** — case studies of players ranked high by Production Sharpe but bottom-quartile by Asset (and vice versa). Names dynasty drafters will recognize.
5. **Positional value patterns** — RB cliff, WR longevity, TE volatility, QB scarcity in superflex.
6. **Projection model coefficients** — what NGS / draft-pick / KTC signals predict outperformance, by position.
7. **Caveats** — KTC isn't literal ADP; small sample (3 cohorts); superflex bias; injuries pull return per spec.

Self-contained HTML output via `rmarkdown::html_document` with `self_contained: true`. Charts directory: `analysis/fantasy_sharpe/charts/`.

## Streamlit view (`views/fantasy_sharpe_projection.py`)

Registered in `components/sidebar.py` under a new entry like "Rookie Projections."

**Sidebar controls:** scoring (PPR / half / std), format (1QB / superflex), position filter.

**Main view:**
- Per-2026-rookie row: name, NFL team, NFL pick, current KTC value, **projected 4-yr PPG share** (floor / median / ceiling from the τ=0.10/0.50/0.90 quantile fits, rendered as bear / base / bull), **projected peak KTC** (same three quantiles), tier-implied Production Sharpe and Asset Sharpe, "exceeds tier expectation by X%" call-out.
- Tier-context drill-in: for any rookie, show distribution of historical comparables in their KTC-rookie-tier — what that tier produced and what it built in asset value.
- No retraining or aggregation in the view. It only loads `projection_model.parquet`.

The view does not require a connected Sleeper league.

## Tests

- **Schema tests** (testthat or pytest, whichever side owns the file): every parquet output has the required columns and types.
- **Sharpe-formula sanity tests**: a small synthetic cohort with known returns produces hand-computed Sharpe values; pipeline result must match.
- **Replacement-rank correctness**: QB24 in superflex, RB24, WR36, TE12 — assert the pipeline picks the right slot.
- **Threshold sync**: the 0.67 hit cutoff is a single source-of-truth constant referenced by both pipeline and Streamlit view. Test that no other code defines a different cutoff.
- **Streamlit smoke test**: `views/fantasy_sharpe_projection.py` imports cleanly, renders without runtime error against a fixture parquet.

## Open items / explicit deferrals

- Live ADP (DDL or Sleeper aggregator) — deferred to v2.
- Real-money confidence on the projection model — sample is tight (3 cohorts × ~15-20 fantasy rookies per position). Coefficients should be presented as directional, not authoritative.
- Sub-1QB-only league formats not in the toggle — superflex coverage only initially.
- TE Premium — not in v1 toggles.

## Risks

- **KTC ≠ ADP.** Tier definitions derived from KTC ranks may diverge from real rookie/startup ADP at the margins. The article will explicitly call this out and invite a v2 swap to true ADP.
- **Small training sample.** 3 cohorts is tight for a regression model. Bootstrap confidence intervals will be reported; coefficients will not be over-interpreted.
- **NGS data joins.** Cross-source player-ID matching has been a pain point in the existing pipeline (the `NICKNAME_ALIASES` table exists for that reason). Plan budgets time for join validation.
