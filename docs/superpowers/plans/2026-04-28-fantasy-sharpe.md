# Fantasy Dynasty Sharpe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the NFL Draft Quasi-Sharpe methodology to dynasty fantasy football. Ship a long-form HTML article on positional value (indexed by KTC-derived rookie & startup ADP) plus a Streamlit projection tool that applies the trained model to the current rookie class.

**Architecture:** R-based data pipeline writes parquet artifacts under `analysis/fantasy_sharpe/data/`. R Markdown article reads those artifacts and renders to self-contained HTML. Python Streamlit view reads the same artifacts (via pyarrow) and renders interactive per-rookie projections. Two parallel Sharpes per cohort: Production (PPG-share, win-now framing) and Asset (peak KTC, rebuild framing).

**Tech Stack:** R 4.x with `tidyverse`, `nflreadr`, `arrow`, `quantreg`, `testthat`, `rmarkdown`. Python 3.12 with `pandas`, `pyarrow`, `streamlit`, `pytest`. Repo: `/Users/nick/projects/dynasty-dashboard`.

**Spec:** `docs/superpowers/specs/2026-04-28-fantasy-sharpe-design.md`

---

## File structure

**New files** (all paths relative to `dynasty-dashboard/`):

- `analysis/fantasy_sharpe/R/constants.R` — single source of truth for tier breaks, replacement ranks, baseline ranks, hit thresholds, eligibility windows.
- `analysis/fantasy_sharpe/R/data_loaders.R` — loaders for fantasy points, NGS, draft picks, KTC current/history.
- `analysis/fantasy_sharpe/R/sharpe_compute.R` — `production_sharpe()` and `asset_sharpe()`, both at player and tier level.
- `analysis/fantasy_sharpe/R/projection_model.R` — feature assembly, per-position elastic-net fit, prediction with bootstrap PI.
- `analysis/fantasy_sharpe/data_pipeline.R` — orchestrator. Sources the four R files above, runs end-to-end, writes parquet outputs.
- `analysis/fantasy_sharpe/analysis.Rmd` — the article. Reads parquet outputs, renders charts and tables, writes self-contained HTML.
- `analysis/fantasy_sharpe/tests/testthat.R` — testthat entry point.
- `analysis/fantasy_sharpe/tests/testthat/test-constants.R`
- `analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R`
- `analysis/fantasy_sharpe/tests/testthat/test-sharpe-compute.R`
- `analysis/fantasy_sharpe/tests/testthat/test-projection-model.R`
- `views/fantasy_sharpe_projection.py` — Streamlit projection view. Reads `projection_model.parquet`, renders sidebar + per-rookie cards + tier-context drill-in.
- `tests/test_fantasy_sharpe_projection.py` — pytest smoke + parquet schema tests.
- `tests/fixtures/fantasy_sharpe_projection_fixture.parquet` — small fixture for view tests.

**Modified files:**

- `ingestion/ktc.py` — add `force_refresh: bool = False` parameter to bypass the existing 7-day TTL cache.
- `ingestion/ktc_history.py` — same.
- `components/sidebar.py` — add `"Rookie Projections"` entry routing to the new view.
- `streamlit_app.py` — add a route block for `selected_tool == "Rookie Projections"`.

**Output artifacts (gitignored):**

- `analysis/fantasy_sharpe/data/fantasy_sharpe.parquet` — player-level historical Sharpe rows.
- `analysis/fantasy_sharpe/data/tier_sharpe.parquet` — tier × position × analysis-type rollups.
- `analysis/fantasy_sharpe/data/projection_model.parquet` — trained coefficients + 2026-rookie features + per-rookie predictions with 95% PI.
- `analysis/fantasy_sharpe/output/*.csv` — CSV mirrors of the above for human inspection.

**Committed artifacts:**

- `analysis/fantasy_sharpe/analysis.html` — rendered article.
- `analysis/fantasy_sharpe/charts/*.png` — figures.

---

## Phase 0: Repository scaffolding

### Task 0.1: Create directory structure

**Files:**
- Create: `analysis/fantasy_sharpe/R/`, `analysis/fantasy_sharpe/data/`, `analysis/fantasy_sharpe/output/`, `analysis/fantasy_sharpe/charts/`, `analysis/fantasy_sharpe/tests/testthat/`

- [ ] **Step 1: Create directories**

```bash
cd /Users/nick/projects/dynasty-dashboard
mkdir -p analysis/fantasy_sharpe/R \
         analysis/fantasy_sharpe/data \
         analysis/fantasy_sharpe/output \
         analysis/fantasy_sharpe/charts \
         analysis/fantasy_sharpe/tests/testthat
```

- [ ] **Step 2: Add data/ and output/ to .gitignore**

Append to `.gitignore` (create if missing):

```
analysis/fantasy_sharpe/data/
analysis/fantasy_sharpe/output/
```

Verify `analysis/fantasy_sharpe/charts/` is NOT ignored (it gets committed).

- [ ] **Step 3: Commit**

```bash
git add .gitignore analysis/fantasy_sharpe/
git commit -m "scaffold: fantasy_sharpe analysis directory"
```

---

## Phase 1: Constants module + tests

### Task 1.1: Define constants with tests

**Files:**
- Create: `analysis/fantasy_sharpe/R/constants.R`
- Create: `analysis/fantasy_sharpe/tests/testthat.R`
- Create: `analysis/fantasy_sharpe/tests/testthat/test-constants.R`

- [ ] **Step 1: Write the failing test**

Create `analysis/fantasy_sharpe/tests/testthat/test-constants.R`:

```r
test_that("ROOKIE_TIER_BREAKS produce 5 labelled buckets", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  expect_length(ROOKIE_TIER_LABELS, 5)
  expect_equal(ROOKIE_TIER_LABELS, c("1.01-1.04", "1.05-1.08", "1.09-1.12", "Round 2", "Round 3+"))
  expect_equal(ROOKIE_TIER_BREAKS, c(0, 4, 8, 12, 24, Inf))
})

test_that("STARTUP_TIER_BREAKS produce 5 labelled buckets", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  expect_length(STARTUP_TIER_LABELS, 5)
  expect_equal(STARTUP_TIER_LABELS, c("Top 12", "13-36", "37-72", "73-150", "151+"))
  expect_equal(STARTUP_TIER_BREAKS, c(0, 12, 36, 72, 150, Inf))
})

test_that("REPLACEMENT_RANK matches superflex 12-team starting lineup", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  expect_equal(REPLACEMENT_RANK[["QB"]], 24)
  expect_equal(REPLACEMENT_RANK[["RB"]], 24)
  expect_equal(REPLACEMENT_RANK[["WR"]], 36)
  expect_equal(REPLACEMENT_RANK[["TE"]], 12)
})

test_that("BASELINE_RANK matches REPLACEMENT_RANK for each position", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  for (pos in c("QB", "RB", "WR", "TE")) {
    expect_equal(BASELINE_RANK[[pos]], REPLACEMENT_RANK[[pos]],
                 info = sprintf("position %s", pos))
  }
})

test_that("HIT_THRESHOLD_SHARE is 0.67", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  expect_equal(HIT_THRESHOLD_SHARE, 0.67)
})

test_that("ELIGIBILITY_COHORTS covers 2020-2022", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  expect_equal(ELIGIBILITY_COHORTS, 2020:2022)
})

test_that("ROOKIE_WINDOW_YEARS is 4", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  expect_equal(ROOKIE_WINDOW_YEARS, 4L)
})

test_that("EXPECTED_GAMES_PER_SEASON is 17", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  expect_equal(EXPECTED_GAMES_PER_SEASON, 17L)
})
```

Create `analysis/fantasy_sharpe/tests/testthat.R`:

```r
library(testthat)
library(here)
test_dir(here::here("analysis/fantasy_sharpe/tests/testthat"), reporter = "summary")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/nick/projects/dynasty-dashboard
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: failures with "could not find" or file-not-found because `constants.R` doesn't exist yet.

- [ ] **Step 3: Implement constants.R**

Create `analysis/fantasy_sharpe/R/constants.R`:

```r
# analysis/fantasy_sharpe/R/constants.R
# Single source of truth for fantasy_sharpe constants.
# Match the superflex 12-team starting lineup convention used throughout the article.

# Tier breaks for the rookie ADP analysis (KTC-derived rookie pick proxy).
# 1.01-1.04 = the four picks with highest at-snapshot KTC superflex value, etc.
ROOKIE_TIER_BREAKS <- c(0, 4, 8, 12, 24, Inf)
ROOKIE_TIER_LABELS <- c("1.01-1.04", "1.05-1.08", "1.09-1.12", "Round 2", "Round 3+")

# Tier breaks for the startup ADP analysis (KTC superflex rank at Aug 1 snapshot).
STARTUP_TIER_BREAKS <- c(0, 12, 36, 72, 150, Inf)
STARTUP_TIER_LABELS <- c("Top 12", "13-36", "37-72", "73-150", "151+")

# Worst-startable positional rank in 12-team superflex.
# Used both as the boundary for the BASELINE_RANK pool (mean PPG of QB1-24 etc.)
# and as the REPLACEMENT_RANK (the actual Nth player at position).
REPLACEMENT_RANK <- list(QB = 24L, RB = 24L, WR = 36L, TE = 12L)
BASELINE_RANK    <- REPLACEMENT_RANK

# Hit threshold: 67% of positional baseline (matches original NFL-Sharpe rule).
HIT_THRESHOLD_SHARE <- 0.67

# Cohorts with completed 4-year fantasy windows AND KTC daily history coverage.
ELIGIBILITY_COHORTS <- 2020:2022

# Years from NFL entry to evaluate.
ROOKIE_WINDOW_YEARS <- 4L

# 17 regular-season games (2021+ schedule). Pre-2021 has 16 — we override per-season
# inside the data loaders, but the default is 17.
EXPECTED_GAMES_PER_SEASON <- 17L

# KTC snapshot dates (relative anchors).
# - rookie_adp: one week after the NFL draft of the rookie's entry year
# - startup_adp: August 1 of any given year
KTC_SNAPSHOT_OFFSET_DAYS_POST_NFL_DRAFT <- 7L

# Positions covered by the analysis.
FANTASY_POSITIONS <- c("QB", "RB", "WR", "TE")
```

- [ ] **Step 4: Run tests to verify pass**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add analysis/fantasy_sharpe/R/constants.R \
        analysis/fantasy_sharpe/tests/testthat.R \
        analysis/fantasy_sharpe/tests/testthat/test-constants.R
git commit -m "feat(fantasy_sharpe): add constants module with tests"
```

---

## Phase 2: KTC ingestion refresh flag

### Task 2.1: Add `force_refresh` flag to `ingestion/ktc.py`

**Files:**
- Modify: `ingestion/ktc.py`
- Test: `tests/test_ktc_force_refresh.py` (create)

- [ ] **Step 1: Read current ktc.py to find the cache check**

```bash
grep -n "ttl\|TTL\|cache_path\|mtime" ingestion/ktc.py
```

Locate the block that checks file mtime against `KTC_TTL_DAYS` (or similar) and short-circuits when the cache is fresh.

- [ ] **Step 2: Write the failing test**

Create `tests/test_ktc_force_refresh.py`:

```python
"""Tests for ingestion.ktc.fetch_ktc force_refresh flag."""
import pytest
from unittest.mock import patch, MagicMock


def test_force_refresh_bypasses_cache(tmp_path, monkeypatch):
    """force_refresh=True must call the network even if the cache is fresh."""
    from ingestion import ktc as ktc_mod

    # Point cache at a tmp file we control
    cache_path = tmp_path / "ktc.parquet"
    cache_path.write_bytes(b"stale")  # exists, fresh by definition (just written)
    monkeypatch.setattr(ktc_mod, "KTC_PARQUET", cache_path, raising=False)

    fake_html = "<html><script>var playersArray = [];</script></html>"
    with patch("ingestion.ktc.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=fake_html)
        # Without force, fresh cache should short-circuit (no network call)
        ktc_mod.fetch_ktc(force_refresh=False)
        assert mock_get.call_count == 0, "fresh cache should short-circuit without force"

        # With force, the network must be called
        ktc_mod.fetch_ktc(force_refresh=True)
        assert mock_get.call_count >= 1, "force_refresh=True must hit the network"


def test_force_refresh_default_is_false():
    """Default behavior must remain unchanged."""
    import inspect
    from ingestion.ktc import fetch_ktc
    sig = inspect.signature(fetch_ktc)
    assert "force_refresh" in sig.parameters
    assert sig.parameters["force_refresh"].default is False
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd /Users/nick/projects/dynasty-dashboard
pytest tests/test_ktc_force_refresh.py -v
```

Expected: FAIL with `TypeError: fetch_ktc() got an unexpected keyword argument 'force_refresh'` or `AssertionError`.

- [ ] **Step 4: Implement the flag**

Open `ingestion/ktc.py`, locate the `fetch_ktc` function. Modify the signature and the cache check:

```python
def fetch_ktc(force_refresh: bool = False) -> pd.DataFrame:
    """Fetch current KTC dynasty rankings. Disk-cached with TTL.

    Args:
        force_refresh: If True, bypass the cache and re-fetch from KTC.
    """
    # ... existing code that defines KTC_PARQUET / cache_path ...

    if not force_refresh and KTC_PARQUET.exists():
        mtime = datetime.fromtimestamp(KTC_PARQUET.stat().st_mtime)
        if datetime.now() - mtime < timedelta(days=KTC_TTL_DAYS):
            return pd.read_parquet(KTC_PARQUET)

    # ... existing network fetch and parse code ...
```

(Adjust to match the actual variable names. The key change is `if not force_refresh and ...` in the cache short-circuit.)

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/test_ktc_force_refresh.py -v
```

Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add ingestion/ktc.py tests/test_ktc_force_refresh.py
git commit -m "feat(ktc): add force_refresh flag to bypass cache"
```

### Task 2.2: Add `force_refresh` flag to `ingestion/ktc_history.py`

**Files:**
- Modify: `ingestion/ktc_history.py`
- Test: `tests/test_ktc_history_force_refresh.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ktc_history_force_refresh.py`:

```python
"""Tests for ingestion.ktc_history.fetch_player_history force_refresh flag."""
import json
from unittest.mock import patch, MagicMock


def test_force_refresh_bypasses_cache(tmp_path, monkeypatch):
    from ingestion import ktc_history as h
    monkeypatch.setattr(h, "KTC_HISTORY_DIR", tmp_path, raising=False)

    cache_file = tmp_path / "365.json"
    cache_file.write_text(json.dumps([{"d": "260101", "v": 9000}]))

    fake_page = "<html>var playerSuperflex = {overallValue: [{d:'260102',v:9100}]};</html>"
    with patch("ingestion.ktc_history.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=fake_page)

        h.fetch_player_history("josh-allen-365", 365, force_refresh=False)
        assert mock_get.call_count == 0

        h.fetch_player_history("josh-allen-365", 365, force_refresh=True)
        assert mock_get.call_count >= 1


def test_default_force_refresh_is_false():
    import inspect
    from ingestion.ktc_history import fetch_player_history
    sig = inspect.signature(fetch_player_history)
    assert "force_refresh" in sig.parameters
    assert sig.parameters["force_refresh"].default is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ktc_history_force_refresh.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement the flag**

Open `ingestion/ktc_history.py`. The function `fetch_player_history(ktc_slug, ktc_id)` already has a TTL check:

```python
if cache_path.exists():
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    if datetime.now() - mtime < timedelta(days=KTC_HISTORY_TTL_DAYS):
        with open(cache_path) as f:
            return json.load(f)
```

Add `force_refresh: bool = False` to the signature and prepend `not force_refresh and` to the outer `if`:

```python
def fetch_player_history(ktc_slug: str, ktc_id: int, force_refresh: bool = False) -> list[dict]:
    KTC_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = KTC_HISTORY_DIR / f"{ktc_id}.json"

    if not force_refresh and cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(days=KTC_HISTORY_TTL_DAYS):
            with open(cache_path) as f:
                return json.load(f)
    # ... rest unchanged ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_ktc_history_force_refresh.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add ingestion/ktc_history.py tests/test_ktc_history_force_refresh.py
git commit -m "feat(ktc_history): add force_refresh flag to bypass cache"
```

### Task 2.3: Refresh KTC data post-NFL-draft

**Files:**
- Modify: `data/ktc.parquet`, `data/ktc_history/*.json` (regenerated)

- [ ] **Step 1: Run a forced refresh**

Create a one-shot script `scripts/refresh_ktc.py` (commit it — useful long-term):

```python
"""Force-refresh KTC current snapshot and per-player history."""
from ingestion.ktc import fetch_ktc
from ingestion.ktc_history import fetch_player_history

print("Refreshing current KTC snapshot...")
df = fetch_ktc(force_refresh=True)
print(f"  {len(df)} players")

print("Refreshing per-player history (this may take ~5-10 minutes)...")
for i, row in enumerate(df.itertuples(index=False)):
    if i % 25 == 0:
        print(f"  {i}/{len(df)}")
    fetch_player_history(row.ktc_slug, int(row.ktc_id), force_refresh=True)

print("Done.")
```

Run:

```bash
python scripts/refresh_ktc.py
```

- [ ] **Step 2: Verify the snapshot is post-NFL-draft**

```bash
python -c "
import pandas as pd
df = pd.read_parquet('data/ktc.parquet')
print(df[df.is_rookie].head(20)[['name','position','team','draft_year','ktc_value','ktc_pos_rank']].to_string())
"
```

Expected: 2026 rookies (e.g., Cam Skattebo, Tetairoa McMillan) with NFL `team` populated (post-draft), not `FA`/empty.

- [ ] **Step 3: Commit the refresh script**

```bash
git add scripts/refresh_ktc.py
git commit -m "feat(scripts): add KTC force-refresh entrypoint"
```

(Do NOT commit `data/ktc.parquet` or `data/ktc_history/*` — they're tracked but should already be refreshed locally for the rest of the plan to work.)

---

## Phase 3: Data loaders

### Task 3.1: Fantasy points loader with tests

**Files:**
- Create: `analysis/fantasy_sharpe/R/data_loaders.R`
- Create: `analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R`

- [ ] **Step 1: Write the failing test**

Create `analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R`:

```r
test_that("load_fantasy_points returns required columns and positive PPG", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  source(here::here("analysis/fantasy_sharpe/R/data_loaders.R"))
  fp <- load_fantasy_points(seasons = 2022)

  expect_true(all(c("player_id", "player_name", "position", "season",
                    "fantasy_points_ppr", "fantasy_points_half",
                    "fantasy_points_std", "games") %in% colnames(fp)))
  expect_true(nrow(fp) > 0)
  expect_true(all(fp$position %in% FANTASY_POSITIONS))
  # Sanity: top QB should have meaningful PPR
  qb_top <- fp |> dplyr::filter(position == "QB") |> dplyr::arrange(desc(fantasy_points_ppr)) |> head(1)
  expect_gt(qb_top$fantasy_points_ppr, 200)
})

test_that("compute_positional_baseline produces per-season per-position scalar", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  source(here::here("analysis/fantasy_sharpe/R/data_loaders.R"))
  fp <- load_fantasy_points(seasons = 2022)
  bl <- compute_positional_baseline(fp, scoring = "half")

  expect_true(all(c("season", "position", "baseline_ppg", "replacement_ppg") %in% colnames(bl)))
  expect_equal(nrow(bl), length(FANTASY_POSITIONS))  # one row per position for one season
  # baseline_ppg should be >= replacement_ppg by construction
  expect_true(all(bl$baseline_ppg >= bl$replacement_ppg - 1e-9))
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: failures because `data_loaders.R` doesn't exist.

- [ ] **Step 3: Implement data_loaders.R (fantasy points + baseline)**

Create `analysis/fantasy_sharpe/R/data_loaders.R`:

```r
# analysis/fantasy_sharpe/R/data_loaders.R
# Loaders for fantasy points, NGS, draft picks, KTC current and history.
# Sources nflreadr; KTC reads from disk artifacts maintained by ingestion/.

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(purrr)
  library(jsonlite)
  library(lubridate)
  library(arrow)
  library(nflreadr)
})

source(here::here("analysis/fantasy_sharpe/R/constants.R"))

# Aggregate weekly stats to season-level fantasy points (PPR/half/std + games).
load_fantasy_points <- function(seasons) {
  ws <- nflreadr::load_player_stats(seasons = seasons, stat_type = "offense")

  ws |>
    mutate(
      fantasy_points_half = fantasy_points + 0.5 * receptions,
      fantasy_points_std  = fantasy_points  # nflreadr's `fantasy_points` is standard
    ) |>
    rename(fantasy_points_ppr = fantasy_points_ppr) |>
    group_by(player_id, player_name, position, season) |>
    summarise(
      fantasy_points_ppr = sum(fantasy_points_ppr, na.rm = TRUE),
      fantasy_points_half = sum(fantasy_points_half, na.rm = TRUE),
      fantasy_points_std  = sum(fantasy_points_std,  na.rm = TRUE),
      games = dplyr::n_distinct(week),
      .groups = "drop"
    ) |>
    filter(position %in% FANTASY_POSITIONS)
}

# For each season × position, compute the mean PPG of the top BASELINE_RANK players
# (the "average startable" baseline) AND the PPG of the player at REPLACEMENT_RANK
# exactly (the worst-startable / FA replacement).
compute_positional_baseline <- function(fp, scoring = c("half", "ppr", "std")) {
  scoring <- match.arg(scoring)
  pts_col <- paste0("fantasy_points_", scoring)

  fp |>
    mutate(ppg = .data[[pts_col]] / pmax(games, 1)) |>
    group_by(season, position) |>
    arrange(desc(ppg), .by_group = TRUE) |>
    mutate(rank = row_number()) |>
    summarise(
      baseline_ppg = mean(ppg[rank <= BASELINE_RANK[[unique(position)]]], na.rm = TRUE),
      replacement_ppg = ppg[rank == REPLACEMENT_RANK[[unique(position)]]][1],
      .groups = "drop"
    )
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: tests pass. (May take ~30s due to nflreadr fetch.)

- [ ] **Step 5: Commit**

```bash
git add analysis/fantasy_sharpe/R/data_loaders.R \
        analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R
git commit -m "feat(fantasy_sharpe): fantasy_points loader + positional baseline"
```

### Task 3.2: KTC history loader with tests

**Files:**
- Modify: `analysis/fantasy_sharpe/R/data_loaders.R` (append)
- Modify: `analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R` (append)

- [ ] **Step 1: Write the failing tests (append)**

Append to `analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R`:

```r
test_that("load_ktc_history returns one row per (ktc_id, date) with parsed Date", {
  source(here::here("analysis/fantasy_sharpe/R/data_loaders.R"))
  hist <- load_ktc_history(here::here("data/ktc_history"))

  expect_true(all(c("ktc_id", "date", "value") %in% colnames(hist)))
  expect_s3_class(hist$date, "Date")
  expect_true(all(hist$value >= 0))
  expect_gt(nrow(hist), 1000)  # Sanity: 290 players × many days
})

test_that("ktc_value_at_date returns the latest value at-or-before the target date", {
  source(here::here("analysis/fantasy_sharpe/R/data_loaders.R"))
  hist <- load_ktc_history(here::here("data/ktc_history"))

  # Take any KTC id that has data
  sample_id <- hist$ktc_id[1]
  target <- max(hist$date[hist$ktc_id == sample_id])
  v <- ktc_value_at_date(hist, sample_id, target)
  expect_true(is.numeric(v) && v >= 0)
  # Future date: should return the latest available
  v_future <- ktc_value_at_date(hist, sample_id, as.Date("2030-01-01"))
  expect_equal(v_future, hist |> dplyr::filter(ktc_id == sample_id) |> dplyr::arrange(desc(date)) |> dplyr::slice(1) |> dplyr::pull(value))
})

test_that("ktc_peak_in_window returns the max value strictly inside the window", {
  source(here::here("analysis/fantasy_sharpe/R/data_loaders.R"))
  hist <- tibble::tribble(
    ~ktc_id, ~date,                 ~value,
    99,      as.Date("2022-01-01"), 5000,
    99,      as.Date("2023-06-15"), 7500,
    99,      as.Date("2024-08-20"), 8200,
    99,      as.Date("2025-11-30"), 6000
  )
  peak <- ktc_peak_in_window(hist, 99, as.Date("2023-01-01"), as.Date("2025-01-01"))
  expect_equal(peak, 8200)
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: failures because the three KTC functions don't exist.

- [ ] **Step 3: Implement KTC loaders (append to data_loaders.R)**

Append to `analysis/fantasy_sharpe/R/data_loaders.R`:

```r
# Load all per-player KTC history JSONs from disk into one tidy frame.
# Each file is a list of {d: "YYMMDD", v: int}.
load_ktc_history <- function(history_dir) {
  files <- list.files(history_dir, pattern = "\\.json$", full.names = TRUE)
  if (length(files) == 0) stop("No KTC history JSON files in ", history_dir)

  parse_one <- function(f) {
    ktc_id <- as.integer(tools::file_path_sans_ext(basename(f)))
    raw <- jsonlite::fromJSON(f, simplifyDataFrame = FALSE)
    if (length(raw) == 0) return(NULL)
    purrr::map_dfr(raw, function(e) {
      tibble::tibble(
        ktc_id = ktc_id,
        date = as.Date(e$d, format = "%y%m%d"),
        value = as.integer(e$v)
      )
    })
  }

  purrr::map_dfr(files, parse_one) |>
    dplyr::filter(!is.na(date), value >= 0)
}

# Get the KTC value at-or-before the target date for a given ktc_id.
# Returns the latest available value strictly <= target. NA if none.
ktc_value_at_date <- function(history, ktc_id_in, target_date) {
  history |>
    dplyr::filter(ktc_id == ktc_id_in, date <= target_date) |>
    dplyr::arrange(desc(date)) |>
    dplyr::slice(1) |>
    dplyr::pull(value) |>
    (\(x) if (length(x) == 0) NA_integer_ else x)()
}

# Peak (max) KTC value in [start_date, end_date] inclusive.
ktc_peak_in_window <- function(history, ktc_id_in, start_date, end_date) {
  history |>
    dplyr::filter(ktc_id == ktc_id_in, date >= start_date, date <= end_date) |>
    dplyr::pull(value) |>
    (\(x) if (length(x) == 0) NA_integer_ else max(x, na.rm = TRUE))()
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: all data_loaders tests pass.

- [ ] **Step 5: Commit**

```bash
git add analysis/fantasy_sharpe/R/data_loaders.R \
        analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R
git commit -m "feat(fantasy_sharpe): KTC history loader and date-range queries"
```

### Task 3.3: Draft picks + NGS loaders with tests

**Files:**
- Modify: `analysis/fantasy_sharpe/R/data_loaders.R` (append)
- Modify: `analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R` (append)

- [ ] **Step 1: Write the failing tests (append)**

Append to `analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R`:

```r
test_that("load_draft_picks_for returns rookies with NFL pick and team", {
  source(here::here("analysis/fantasy_sharpe/R/data_loaders.R"))
  dp <- load_draft_picks_for(2022)
  expect_true(all(c("season", "pick", "round", "team", "gsis_id",
                    "pfr_player_name", "position") %in% colnames(dp)))
  expect_true(all(dp$position %in% c(FANTASY_POSITIONS, "FB")))  # FB shows up sometimes
  expect_true(nrow(dp) > 20)  # At least 20 fantasy-relevant rookies in any draft
})

test_that("load_ngs_features returns one row per draft prospect with measurables", {
  source(here::here("analysis/fantasy_sharpe/R/data_loaders.R"))
  ngs <- load_ngs_features(c(2020, 2021, 2022))
  # Required cols (with NAs allowed)
  expect_true(all(c("draft_year", "player_name", "pos",
                    "ras", "forty", "vertical", "broad_jump",
                    "weight", "height") %in% colnames(ngs)))
  expect_true(nrow(ngs) > 50)  # Sanity check — combine has hundreds of prospects per year
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: failures.

- [ ] **Step 3: Implement loaders (append)**

Append to `analysis/fantasy_sharpe/R/data_loaders.R`:

```r
load_draft_picks_for <- function(seasons) {
  nflreadr::load_draft_picks() |>
    dplyr::filter(season %in% seasons) |>
    dplyr::filter(position %in% c(FANTASY_POSITIONS, "FB")) |>
    dplyr::transmute(
      season, round, pick,
      team = case_when(
        team %in% c("STL", "SL", "LAR") ~ "LA",
        team %in% c("OAK", "LVR") ~ "LV",
        team %in% c("SDG", "SD") ~ "LAC",
        TRUE ~ team
      ),
      gsis_id, pfr_player_id, pfr_player_name,
      position
    )
}

# Pull combine measurables and athletic scores. RAS is computed from the underlying
# combine fields by nflreadr; if nflreadr lacks RAS for a given prospect we leave it NA
# and let the projection model handle missingness via complete-case fits.
load_ngs_features <- function(seasons) {
  c <- nflreadr::load_combine(seasons = seasons)
  c |>
    dplyr::transmute(
      draft_year = season,
      player_name = player_name,
      pos = pos,
      ras = ras,
      forty = forty_yard_dash,
      vertical = vertical_jump,
      broad_jump = broad_jump,
      weight = weight,
      height = height,
      bench_press = bench_press,
      cone = three_cone,
      shuttle = shuttle
    )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: all 7 data_loaders tests pass. NGS test may need column-name adjustments — check `nflreadr::dictionary_combine` for current schema and tweak if `forty_yard_dash` is named differently. Update the loader and the test together if so.

- [ ] **Step 5: Commit**

```bash
git add analysis/fantasy_sharpe/R/data_loaders.R \
        analysis/fantasy_sharpe/tests/testthat/test-data-loaders.R
git commit -m "feat(fantasy_sharpe): draft picks and NGS combine loaders"
```

---

## Phase 4: Sharpe computation

### Task 4.1: Production Sharpe with tests

**Files:**
- Create: `analysis/fantasy_sharpe/R/sharpe_compute.R`
- Create: `analysis/fantasy_sharpe/tests/testthat/test-sharpe-compute.R`

- [ ] **Step 1: Write the failing test**

Create `analysis/fantasy_sharpe/tests/testthat/test-sharpe-compute.R`:

```r
test_that("compute_player_production_share gives the expected share for a synthetic cohort", {
  source(here::here("analysis/fantasy_sharpe/R/constants.R"))
  source(here::here("analysis/fantasy_sharpe/R/sharpe_compute.R"))

  # Player A: 1000 PPR over 4 seasons, 17 games each season expected.
  # Total PPG = 1000 / (4 * 17) = 14.71.
  # If positional baseline averaged across the 4 seasons is 14.71, share = 1.0.
  player_seasons <- tibble::tibble(
    player_id = "A",
    season = 2020:2023,
    position = "WR",
    fantasy_points_half = c(250, 250, 250, 250),  # 1000 total
    games = c(17, 17, 17, 17)
  )
  baseline <- tibble::tibble(
    season = 2020:2023, position = "WR",
    baseline_ppg = 14.71, replacement_ppg = 10.0
  )

  share <- compute_player_production_share(player_seasons, baseline,
                                           scoring = "half",
                                           rookie_year = 2020)
  expect_equal(share$ppg_share, 1.0, tolerance = 0.01)
  expect_equal(share$replacement_share, 10.0 / 14.71, tolerance = 0.01)
  expect_true(share$is_hit)  # 1.0 >= 0.67
})

test_that("tier_production_sharpe returns one row per (position, tier)", {
  source(here::here("analysis/fantasy_sharpe/R/sharpe_compute.R"))
  player_df <- tibble::tibble(
    position = c("WR", "WR", "WR", "RB", "RB"),
    tier = factor(c("1.01-1.04", "1.01-1.04", "Round 2", "1.05-1.08", "1.05-1.08"),
                  levels = c("1.01-1.04", "1.05-1.08", "1.09-1.12", "Round 2", "Round 3+")),
    ppg_share = c(1.2, 0.9, 0.4, 0.7, 1.1),
    replacement_share = 0.6,
    is_hit = c(TRUE, TRUE, FALSE, TRUE, TRUE)
  )
  out <- tier_production_sharpe(player_df)
  expect_true(all(c("position", "tier", "n", "hit_rate", "mean_share",
                    "sd_share", "sharpe_linear", "sharpe_elite") %in% colnames(out)))
  expect_equal(nrow(out), 3)  # Three (position, tier) combinations in the input
})

test_that("sharpe_linear formula matches by-hand calculation", {
  source(here::here("analysis/fantasy_sharpe/R/sharpe_compute.R"))
  player_df <- tibble::tibble(
    position = "WR",
    tier = factor("1.01-1.04", levels = c("1.01-1.04", "1.05-1.08", "1.09-1.12", "Round 2", "Round 3+")),
    ppg_share = c(0.5, 1.0, 1.5),  # mean 1.0, sd ~0.5
    replacement_share = 0.6,
    is_hit = c(FALSE, TRUE, TRUE)
  )
  out <- tier_production_sharpe(player_df)
  expect_equal(out$mean_share, 1.0, tolerance = 1e-9)
  expect_equal(out$sd_share, sd(c(0.5, 1.0, 1.5)), tolerance = 1e-9)
  expected_sharpe <- (1.0 - 0.6) / sd(c(0.5, 1.0, 1.5))
  expect_equal(out$sharpe_linear, expected_sharpe, tolerance = 1e-9)
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: failures because sharpe_compute.R doesn't exist.

- [ ] **Step 3: Implement sharpe_compute.R**

Create `analysis/fantasy_sharpe/R/sharpe_compute.R`:

```r
# analysis/fantasy_sharpe/R/sharpe_compute.R
# Production Sharpe (PPG-share) and Asset Sharpe (peak KTC). Both at player and tier level.

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
})
source(here::here("analysis/fantasy_sharpe/R/constants.R"))

# For one player (one row per season in their rookie window): compute the 4-year
# PPG share, the season-averaged replacement share, and the hit flag.
compute_player_production_share <- function(player_seasons, baseline_df,
                                            scoring = c("half", "ppr", "std"),
                                            rookie_year) {
  scoring <- match.arg(scoring)
  pts_col <- paste0("fantasy_points_", scoring)

  player_seasons <- player_seasons |>
    dplyr::filter(season >= rookie_year, season < rookie_year + ROOKIE_WINDOW_YEARS)

  total_pts <- sum(player_seasons[[pts_col]], na.rm = TRUE)
  expected_games <- ROOKIE_WINDOW_YEARS * EXPECTED_GAMES_PER_SEASON
  player_ppg <- total_pts / expected_games

  bl_window <- baseline_df |>
    dplyr::filter(season >= rookie_year,
                  season < rookie_year + ROOKIE_WINDOW_YEARS,
                  position == unique(player_seasons$position))

  baseline_avg <- mean(bl_window$baseline_ppg, na.rm = TRUE)
  replacement_avg <- mean(bl_window$replacement_ppg, na.rm = TRUE)

  ppg_share <- player_ppg / baseline_avg
  replacement_share <- replacement_avg / baseline_avg

  tibble::tibble(
    player_id = unique(player_seasons$player_id),
    position = unique(player_seasons$position),
    rookie_year = rookie_year,
    player_ppg = player_ppg,
    baseline_ppg = baseline_avg,
    replacement_ppg = replacement_avg,
    ppg_share = ppg_share,
    replacement_share = replacement_share,
    is_hit = ppg_share >= HIT_THRESHOLD_SHARE
  )
}

# Aggregate to (position, tier).
tier_production_sharpe <- function(player_df) {
  player_df |>
    dplyr::filter(!is.na(ppg_share)) |>
    dplyr::group_by(position, tier) |>
    dplyr::summarise(
      n = dplyr::n(),
      hit_rate = mean(is_hit, na.rm = TRUE),
      mean_share = mean(ppg_share, na.rm = TRUE),
      sd_share = stats::sd(ppg_share, na.rm = TRUE),
      replacement_share = mean(replacement_share, na.rm = TRUE),
      elite_threshold = stats::quantile(player_df$ppg_share[player_df$ppg_share > 0],
                                        probs = 0.9, na.rm = TRUE),
      elite_prob = mean(ppg_share >= stats::quantile(player_df$ppg_share[player_df$ppg_share > 0],
                                                     probs = 0.9, na.rm = TRUE), na.rm = TRUE),
      .groups = "drop"
    ) |>
    dplyr::mutate(
      sharpe_linear = (mean_share - replacement_share) / sd_share,
      sharpe_elite  = (elite_prob * elite_threshold - replacement_share) / sd_share
    ) |>
    dplyr::mutate(across(starts_with("sharpe_"), \(x) ifelse(is.finite(x), x, NA_real_)))
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: all 3 sharpe_compute tests pass.

- [ ] **Step 5: Commit**

```bash
git add analysis/fantasy_sharpe/R/sharpe_compute.R \
        analysis/fantasy_sharpe/tests/testthat/test-sharpe-compute.R
git commit -m "feat(fantasy_sharpe): production Sharpe (player + tier)"
```

### Task 4.2: Asset Sharpe with tests

**Files:**
- Modify: `analysis/fantasy_sharpe/R/sharpe_compute.R` (append)
- Modify: `analysis/fantasy_sharpe/tests/testthat/test-sharpe-compute.R` (append)

- [ ] **Step 1: Write the failing test (append)**

Append to `test-sharpe-compute.R`:

```r
test_that("compute_player_asset_value finds peak KTC during rookie window", {
  source(here::here("analysis/fantasy_sharpe/R/sharpe_compute.R"))
  hist <- tibble::tribble(
    ~ktc_id, ~date,                 ~value,
    77,      as.Date("2020-09-15"), 5000,
    77,      as.Date("2021-12-01"), 8000,
    77,      as.Date("2023-08-20"), 9500,  # peak inside window
    77,      as.Date("2024-01-10"), 7000,
    77,      as.Date("2025-06-01"), 6000   # outside 4-year window starting 2020
  )
  result <- compute_player_asset_value(
    history = hist, ktc_id = 77, rookie_year = 2020,
    replacement_ktc_by_season = tibble::tibble(season = 2020:2023, replacement_ktc = 4000)
  )
  expect_equal(result$peak_ktc, 9500)
  expect_equal(result$replacement_ktc, 4000)
  expect_true(result$is_asset_hit)  # 9500 >= 4000
})

test_that("tier_asset_sharpe formula", {
  source(here::here("analysis/fantasy_sharpe/R/sharpe_compute.R"))
  player_df <- tibble::tibble(
    position = "WR",
    tier = factor("1.01-1.04", levels = c("1.01-1.04", "1.05-1.08", "1.09-1.12", "Round 2", "Round 3+")),
    peak_ktc = c(5000, 7000, 9000),
    replacement_ktc = 4000,
    is_asset_hit = c(TRUE, TRUE, TRUE)
  )
  out <- tier_asset_sharpe(player_df)
  expect_equal(out$mean_peak_ktc, 7000)
  expect_equal(out$sharpe_linear,
               (7000 - 4000) / sd(c(5000, 7000, 9000)),
               tolerance = 1e-9)
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: failures.

- [ ] **Step 3: Implement asset Sharpe (append to sharpe_compute.R)**

Append to `analysis/fantasy_sharpe/R/sharpe_compute.R`:

```r
compute_player_asset_value <- function(history, ktc_id, rookie_year,
                                       replacement_ktc_by_season) {
  start_date <- as.Date(sprintf("%d-09-01", rookie_year))
  end_date   <- as.Date(sprintf("%d-08-31", rookie_year + ROOKIE_WINDOW_YEARS - 1))

  peak <- history |>
    dplyr::filter(ktc_id == !!ktc_id, date >= start_date, date <= end_date) |>
    dplyr::pull(value) |>
    (\(x) if (length(x) == 0) NA_integer_ else max(x, na.rm = TRUE))()

  replacement <- replacement_ktc_by_season |>
    dplyr::filter(season >= rookie_year, season < rookie_year + ROOKIE_WINDOW_YEARS) |>
    dplyr::pull(replacement_ktc) |>
    mean(na.rm = TRUE)

  tibble::tibble(
    ktc_id = ktc_id,
    rookie_year = rookie_year,
    peak_ktc = peak,
    replacement_ktc = replacement,
    is_asset_hit = !is.na(peak) & peak >= replacement
  )
}

tier_asset_sharpe <- function(player_df) {
  player_df |>
    dplyr::filter(!is.na(peak_ktc)) |>
    dplyr::group_by(position, tier) |>
    dplyr::summarise(
      n = dplyr::n(),
      asset_hit_rate = mean(is_asset_hit, na.rm = TRUE),
      mean_peak_ktc = mean(peak_ktc, na.rm = TRUE),
      sd_peak_ktc = stats::sd(peak_ktc, na.rm = TRUE),
      replacement_ktc = mean(replacement_ktc, na.rm = TRUE),
      elite_threshold_ktc = stats::quantile(player_df$peak_ktc[player_df$peak_ktc > 0],
                                            probs = 0.9, na.rm = TRUE),
      elite_prob_ktc = mean(peak_ktc >= stats::quantile(player_df$peak_ktc[player_df$peak_ktc > 0],
                                                        probs = 0.9, na.rm = TRUE), na.rm = TRUE),
      .groups = "drop"
    ) |>
    dplyr::mutate(
      sharpe_linear = (mean_peak_ktc - replacement_ktc) / sd_peak_ktc,
      sharpe_elite  = (elite_prob_ktc * elite_threshold_ktc - replacement_ktc) / sd_peak_ktc
    ) |>
    dplyr::mutate(across(starts_with("sharpe_"), \(x) ifelse(is.finite(x), x, NA_real_)))
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: all 5 sharpe_compute tests pass.

- [ ] **Step 5: Commit**

```bash
git add analysis/fantasy_sharpe/R/sharpe_compute.R \
        analysis/fantasy_sharpe/tests/testthat/test-sharpe-compute.R
git commit -m "feat(fantasy_sharpe): asset Sharpe (peak KTC, player + tier)"
```

---

## Phase 5: Pipeline orchestration

### Task 5.1: Wire data_pipeline.R end-to-end

**Files:**
- Create: `analysis/fantasy_sharpe/data_pipeline.R`

- [ ] **Step 1: Write the orchestrator**

Create `analysis/fantasy_sharpe/data_pipeline.R`:

```r
# analysis/fantasy_sharpe/data_pipeline.R
# Orchestrator. Loads inputs, computes both Sharpes for the rookie-ADP and
# startup-ADP analyses, writes parquet artifacts under analysis/fantasy_sharpe/data/.

suppressPackageStartupMessages({
  library(dplyr)
  library(here)
  library(arrow)
})

source(here("analysis/fantasy_sharpe/R/constants.R"))
source(here("analysis/fantasy_sharpe/R/data_loaders.R"))
source(here("analysis/fantasy_sharpe/R/sharpe_compute.R"))

cat("[fantasy_sharpe] Loading inputs...\n")

# Fantasy points across all seasons we need (rookie window for the latest cohort).
all_seasons <- min(ELIGIBILITY_COHORTS):(max(ELIGIBILITY_COHORTS) + ROOKIE_WINDOW_YEARS - 1)
fp <- load_fantasy_points(seasons = all_seasons)
baseline <- compute_positional_baseline(fp, scoring = "half")

# Draft picks for the eligibility cohorts.
draft <- load_draft_picks_for(ELIGIBILITY_COHORTS)
cat(sprintf("  rookies: %d\n", nrow(draft)))

# KTC history.
ktc_hist <- load_ktc_history(here("data/ktc_history"))
ktc_now <- arrow::read_parquet(here("data/ktc.parquet"))
cat(sprintf("  ktc rows: %d\n", nrow(ktc_hist)))

# Player ID bridge: KTC -> nflreadr (gsis_id). Use nflreadr ff_playerids.
ids <- nflreadr::load_ff_playerids() |>
  dplyr::transmute(ktc_id = as.integer(ktcid),
                   gsis_id, mfl_id = as.integer(mfl_id), name)

# Build the rookie roster: join draft picks to KTC ids (via name + position fallback to mfl).
rookies <- draft |>
  dplyr::left_join(
    ktc_now |> dplyr::select(name, position, ktc_id, mfl_id, draft_year, ktc_value, ktc_pos_rank),
    by = c("pfr_player_name" = "name", "position" = "position")
  ) |>
  dplyr::filter(!is.na(ktc_id))

cat(sprintf("  matched to KTC: %d\n", nrow(rookies)))

# Tier assignment via KTC pos_rank at one-week-post-NFL-draft snapshot.
# (Approximation: use ktc_pos_rank from the current snapshot as proxy for the
# one-week-post-NFL-draft rank for the 2026 cohort. For 2020-2022 we'd need to
# look up KTC pos rank as of that historical date — implemented via ktc_value_at_date.)
nfl_draft_dates <- tibble::tribble(
  ~season, ~draft_end,
  2020,    as.Date("2020-04-25"),
  2021,    as.Date("2021-05-01"),
  2022,    as.Date("2022-04-30"),
  2023,    as.Date("2023-04-29"),
  2024,    as.Date("2024-04-27"),
  2025,    as.Date("2025-04-26"),
  2026,    as.Date("2026-04-25")  # adjust if needed
) |>
  dplyr::mutate(snapshot_date = draft_end + KTC_SNAPSHOT_OFFSET_DAYS_POST_NFL_DRAFT)

# Replace ktc_value with the snapshot-date value for each rookie.
rookies <- rookies |>
  dplyr::left_join(nfl_draft_dates, by = "season") |>
  dplyr::rowwise() |>
  dplyr::mutate(
    ktc_value_snapshot = ktc_value_at_date(ktc_hist, ktc_id, snapshot_date)
  ) |>
  dplyr::ungroup()

# Within each (season, position), rank by ktc_value_snapshot to produce a position-rank
# at the one-week-post-NFL-draft snapshot. Used for the rookie-ADP tier assignment.
rookies <- rookies |>
  dplyr::group_by(season, position) |>
  dplyr::mutate(rookie_pos_rank = dplyr::row_number(dplyr::desc(ktc_value_snapshot))) |>
  dplyr::ungroup() |>
  dplyr::group_by(season) |>
  dplyr::mutate(
    rookie_overall_rank = dplyr::row_number(dplyr::desc(ktc_value_snapshot)),
    tier_rookie = cut(rookie_overall_rank,
                      breaks = ROOKIE_TIER_BREAKS,
                      labels = ROOKIE_TIER_LABELS,
                      right = TRUE)
  ) |>
  dplyr::ungroup()

cat("[fantasy_sharpe] Computing production Sharpe (rookie ADP)...\n")

# For each rookie we have a window. Compute production share.
production_rows <- rookies |>
  dplyr::rowwise() |>
  dplyr::mutate(
    player_seasons_df = list(fp |> dplyr::filter(player_name == pfr_player_name,
                                                 position == position,
                                                 season >= season,
                                                 season < season + ROOKIE_WINDOW_YEARS)),
    share_row = list({
      ps <- player_seasons_df
      if (nrow(ps) == 0) {
        tibble::tibble(player_id = NA_character_, position = position,
                       rookie_year = season, player_ppg = NA_real_,
                       baseline_ppg = NA_real_, replacement_ppg = NA_real_,
                       ppg_share = NA_real_, replacement_share = NA_real_,
                       is_hit = NA)
      } else {
        compute_player_production_share(ps, baseline, scoring = "half", rookie_year = season)
      }
    })
  ) |>
  dplyr::ungroup() |>
  tidyr::unnest(share_row, names_repair = "minimal") |>
  dplyr::select(-player_seasons_df)

cat("[fantasy_sharpe] Computing asset Sharpe (rookie ADP)...\n")

# Replacement KTC by season: average KTC value of position-rank=REPLACEMENT_RANK at
# season-start, using ktc_now as proxy. (Approximation; refine in v2.)
replacement_ktc <- ktc_now |>
  dplyr::filter(position %in% FANTASY_POSITIONS) |>
  dplyr::group_by(position) |>
  dplyr::filter(ktc_pos_rank == REPLACEMENT_RANK[[unique(position)]]) |>
  dplyr::summarise(replacement_ktc = mean(ktc_value), .groups = "drop")

# Build per-season replacement_ktc by joining current rep value as a constant
# (proxy — a true historical version would compute rank=N KTC at each historical date).
replacement_ktc_by_season <- tidyr::expand_grid(
  season = all_seasons, position = FANTASY_POSITIONS
) |>
  dplyr::left_join(replacement_ktc, by = "position")

asset_rows <- rookies |>
  dplyr::rowwise() |>
  dplyr::mutate(
    asset_row = list(compute_player_asset_value(
      ktc_hist, ktc_id, rookie_year = season,
      replacement_ktc_by_season = replacement_ktc_by_season |>
        dplyr::filter(position == position)
    ))
  ) |>
  dplyr::ungroup() |>
  tidyr::unnest(asset_row, names_repair = "minimal")

# Combine and write player-level frame.
player_frame <- production_rows |>
  dplyr::left_join(
    asset_rows |> dplyr::select(ktc_id, peak_ktc, replacement_ktc, is_asset_hit),
    by = "ktc_id"
  ) |>
  dplyr::select(season, pfr_player_name, position, ktc_id, ktc_value_snapshot,
                rookie_overall_rank, rookie_pos_rank, tier_rookie,
                player_ppg, baseline_ppg, replacement_ppg, ppg_share, replacement_share, is_hit,
                peak_ktc, replacement_ktc, is_asset_hit)

cat("[fantasy_sharpe] Aggregating tier-level Sharpe...\n")

tier_prod <- player_frame |>
  dplyr::rename(tier = tier_rookie) |>
  tier_production_sharpe() |>
  dplyr::mutate(analysis = "rookie_adp", sharpe_kind = "production")

tier_asset <- player_frame |>
  dplyr::rename(tier = tier_rookie) |>
  tier_asset_sharpe() |>
  dplyr::mutate(analysis = "rookie_adp", sharpe_kind = "asset")

tier_frame <- dplyr::bind_rows(tier_prod, tier_asset)

# Write outputs.
arrow::write_parquet(player_frame, here("analysis/fantasy_sharpe/data/fantasy_sharpe.parquet"))
arrow::write_parquet(tier_frame, here("analysis/fantasy_sharpe/data/tier_sharpe.parquet"))
readr::write_csv(player_frame, here("analysis/fantasy_sharpe/output/fantasy_sharpe.csv"))
readr::write_csv(tier_frame, here("analysis/fantasy_sharpe/output/tier_sharpe.csv"))

cat("[fantasy_sharpe] Done. ", nrow(player_frame), "player rows,", nrow(tier_frame), "tier rows.\n")
```

- [ ] **Step 2: Run the pipeline**

```bash
cd /Users/nick/projects/dynasty-dashboard
Rscript analysis/fantasy_sharpe/data_pipeline.R
```

Expected: completes in ~1-3 minutes (network fetches via nflreadr). Writes 4 files. If failures occur on the player-id join, check `nflreadr::load_ff_playerids()` schema and adjust the join on the closest of `gsis_id` / `pfr_player_id` / `name + position`.

- [ ] **Step 3: Verify outputs**

```bash
python3 -c "
import pandas as pd
p = pd.read_parquet('analysis/fantasy_sharpe/data/fantasy_sharpe.parquet')
t = pd.read_parquet('analysis/fantasy_sharpe/data/tier_sharpe.parquet')
print('player rows:', len(p))
print('tier rows:', len(t))
print('positions:', p.position.value_counts().to_dict())
print('seasons:', sorted(p.season.unique()))
print(t.head(10).to_string())
"
```

Expected: ~120-180 player rows, ~24-40 tier rows (5 tiers × 4 positions × 2 sharpe kinds), seasons 2020-2022.

- [ ] **Step 4: Commit**

```bash
git add analysis/fantasy_sharpe/data_pipeline.R
git commit -m "feat(fantasy_sharpe): orchestrator pipeline (rookie ADP only)"
```

### Task 5.2: Add startup-ADP analysis branch

**Files:**
- Modify: `analysis/fantasy_sharpe/data_pipeline.R`

- [ ] **Step 1: Add startup-ADP block**

Append the following block to `data_pipeline.R` *before* the final write section. Then move the writes to the end:

```r
cat("[fantasy_sharpe] Computing startup-ADP analysis...\n")

# Snapshot dates: August 1 of each cohort year. For each player active that summer,
# compute KTC pos_rank (overall) on Aug 1, assign tier from STARTUP_TIER_BREAKS.
startup_snapshots <- tibble::tibble(
  season = ELIGIBILITY_COHORTS,
  snapshot_date = as.Date(sprintf("%d-08-01", ELIGIBILITY_COHORTS))
)

# For each season, get every player's KTC value on Aug 1 → rank → tier.
build_startup_for_season <- function(snap_date, snap_season) {
  ktc_now |>
    dplyr::filter(position %in% FANTASY_POSITIONS) |>
    dplyr::rowwise() |>
    dplyr::mutate(value_at = ktc_value_at_date(ktc_hist, ktc_id, snap_date)) |>
    dplyr::ungroup() |>
    dplyr::filter(!is.na(value_at), value_at > 0) |>
    dplyr::mutate(season = snap_season,
                  startup_overall_rank = dplyr::row_number(dplyr::desc(value_at)),
                  tier_startup = cut(startup_overall_rank,
                                     breaks = STARTUP_TIER_BREAKS,
                                     labels = STARTUP_TIER_LABELS,
                                     right = TRUE))
}

startup_pool <- purrr::pmap_dfr(
  list(startup_snapshots$snapshot_date, startup_snapshots$season),
  build_startup_for_season
)

# For each (player, season) in startup_pool, compute production from that
# season forward 4 years and peak KTC in that 4-year window.
# Joins by player name to fantasy points; unmatched rows are dropped.
startup_production_inputs <- startup_pool |>
  dplyr::select(season_window_start = season, pfr_player_name = name, position,
                tier_startup, startup_overall_rank, ktc_id) |>
  dplyr::inner_join(
    fp |> dplyr::select(player_name, position, season,
                        fantasy_points_half, games),
    by = c("pfr_player_name" = "player_name", "position" = "position")
  ) |>
  dplyr::filter(season >= season_window_start,
                season < season_window_start + ROOKIE_WINDOW_YEARS)

startup_production <- startup_production_inputs |>
  dplyr::group_by(pfr_player_name, position, season_window_start, tier_startup, ktc_id) |>
  dplyr::summarise(
    total_points_half = sum(fantasy_points_half, na.rm = TRUE),
    .groups = "drop"
  ) |>
  dplyr::left_join(
    baseline |> dplyr::select(season, position, baseline_ppg, replacement_ppg),
    by = c("position", "season_window_start" = "season")
  ) |>
  dplyr::mutate(
    player_ppg = total_points_half / (ROOKIE_WINDOW_YEARS * EXPECTED_GAMES_PER_SEASON),
    ppg_share = player_ppg / baseline_ppg,
    replacement_share = replacement_ppg / baseline_ppg,
    is_hit = ppg_share >= HIT_THRESHOLD_SHARE
  )

startup_asset <- startup_pool |>
  dplyr::rowwise() |>
  dplyr::mutate(
    asset_row = list(compute_player_asset_value(
      ktc_hist, ktc_id, rookie_year = season,
      replacement_ktc_by_season = replacement_ktc_by_season |>
        dplyr::filter(position == .env$position)
    ))
  ) |>
  dplyr::ungroup() |>
  tidyr::unnest(asset_row, names_repair = "minimal") |>
  dplyr::select(ktc_id, peak_ktc, replacement_ktc, is_asset_hit, tier_startup, position)

startup_player_frame <- startup_production |>
  dplyr::left_join(
    startup_asset |> dplyr::select(ktc_id, peak_ktc, replacement_ktc, is_asset_hit),
    by = "ktc_id"
  )

tier_startup_prod <- startup_player_frame |>
  dplyr::rename(tier = tier_startup) |>
  tier_production_sharpe() |>
  dplyr::mutate(analysis = "startup_adp", sharpe_kind = "production")

tier_startup_asset <- startup_player_frame |>
  dplyr::rename(tier = tier_startup) |>
  tier_asset_sharpe() |>
  dplyr::mutate(analysis = "startup_adp", sharpe_kind = "asset")

tier_frame <- dplyr::bind_rows(tier_frame, tier_startup_prod, tier_startup_asset)
```

- [ ] **Step 2: Run the pipeline**

```bash
Rscript analysis/fantasy_sharpe/data_pipeline.R
```

Expected: completes; tier_frame now has rows for both `analysis ∈ {rookie_adp, startup_adp}`.

- [ ] **Step 3: Verify**

```bash
python3 -c "
import pandas as pd
t = pd.read_parquet('analysis/fantasy_sharpe/data/tier_sharpe.parquet')
print(t.groupby(['analysis','sharpe_kind']).size())
"
```

Expected: 4 row-counts, one for each (analysis × sharpe_kind) combination.

- [ ] **Step 4: Commit**

```bash
git add analysis/fantasy_sharpe/data_pipeline.R
git commit -m "feat(fantasy_sharpe): add startup-ADP analysis branch"
```

---

## Phase 6: Projection model (quantile regression)

### Task 6.1: Feature assembly + quantile-regression model with tests

**Files:**
- Create: `analysis/fantasy_sharpe/R/projection_model.R`
- Create: `analysis/fantasy_sharpe/tests/testthat/test-projection-model.R`

**Methodology note:** Mirrors the existing draft-Sharpe counter-analysis (`R/grader_projection.R` in the original `draft-sharpe-analysis` repo): per-position quantile regression at τ ∈ {0.10, 0.50, 0.90} produces floor / median / ceiling outcomes. Falls back to empirical positional quantiles when features are missing.

- [ ] **Step 1: Write the failing test**

Create `analysis/fantasy_sharpe/tests/testthat/test-projection-model.R`:

```r
test_that("assemble_features joins draft picks, NGS, KTC into one frame per rookie", {
  source(here::here("analysis/fantasy_sharpe/R/projection_model.R"))
  draft <- tibble::tibble(season = 2022, pfr_player_name = "Drake London",
                          position = "WR", pick = 8L, gsis_id = "00-0037216")
  ngs <- tibble::tibble(draft_year = 2022, player_name = "Drake London", pos = "WR",
                        ras = 8.1, forty = 4.55, vertical = 36, broad_jump = 119,
                        weight = 213, height = 76)
  ktc_snapshot <- tibble::tibble(pfr_player_name = "Drake London",
                                 ktc_value_snapshot = 7000)

  feats <- assemble_features(draft, ngs, ktc_snapshot)
  expect_equal(nrow(feats), 1)
  expect_true(all(c("ras", "forty", "vertical", "broad_jump", "pick",
                    "ktc_value_snapshot", "position", "rookie_year") %in% colnames(feats)))
  expect_equal(feats$ras, 8.1)
  expect_equal(feats$pick, 8L)
})

test_that("fit_quantile_models returns one rq fit per position per tau", {
  source(here::here("analysis/fantasy_sharpe/R/projection_model.R"))

  set.seed(42)
  n <- 30
  fake <- tibble::tibble(
    position = rep(c("WR", "RB"), each = n / 2),
    rookie_year = rep(c(2020, 2021, 2022), length.out = n),
    pick = sample(1:200, n),
    ras = runif(n, 4, 10),
    forty = runif(n, 4.3, 4.8),
    vertical = runif(n, 28, 42),
    weight = runif(n, 180, 240),
    ktc_value_snapshot = sample(2000:9000, n),
    target_ppg_share = runif(n, 0.1, 1.5)
  )

  models <- fit_quantile_models(fake, target = "target_ppg_share")
  # Expect named list per position, each containing q10/q50/q90 fits.
  expect_named(models, c("WR", "RB"), ignore.order = TRUE)
  for (pos in names(models)) {
    expect_named(models[[pos]]$fits, c("q10", "q50", "q90"), ignore.order = TRUE)
    # Each fit is either an rq object or NULL (fallback)
    for (q in c("q10", "q50", "q90")) {
      f <- models[[pos]]$fits[[q]]
      expect_true(inherits(f, "rq") || is.null(f))
    }
    # Empirical fallback quantiles should always be present
    expect_true(all(c("floor", "median", "ceiling") %in% names(models[[pos]]$empirical)))
  }
})

test_that("predict_quantile_projection returns floor, median, ceiling per row", {
  source(here::here("analysis/fantasy_sharpe/R/projection_model.R"))

  set.seed(7)
  n <- 30
  fake <- tibble::tibble(
    position = rep("WR", n),
    rookie_year = rep(c(2020, 2021, 2022), length.out = n),
    pick = sample(1:200, n),
    ras = runif(n, 4, 10),
    forty = runif(n, 4.3, 4.8),
    vertical = runif(n, 28, 42),
    weight = runif(n, 180, 240),
    ktc_value_snapshot = sample(2000:9000, n),
    target_ppg_share = runif(n, 0.1, 1.5)
  )
  models <- fit_quantile_models(fake, target = "target_ppg_share")

  newdata <- fake[1, , drop = FALSE]
  preds <- predict_quantile_projection(models, newdata)
  expect_equal(nrow(preds), 1)
  expect_true(all(c("floor", "median", "ceiling") %in% colnames(preds)))
  # Floor must be <= median <= ceiling (after monotonization)
  expect_lte(preds$floor, preds$median)
  expect_lte(preds$median, preds$ceiling)
})

test_that("predict_quantile_projection falls back to empirical quantiles when features missing", {
  source(here::here("analysis/fantasy_sharpe/R/projection_model.R"))

  set.seed(11)
  n <- 30
  train <- tibble::tibble(
    position = rep("WR", n),
    pick = sample(1:200, n),
    ras = runif(n, 4, 10),
    forty = runif(n, 4.3, 4.8),
    vertical = runif(n, 28, 42),
    weight = runif(n, 180, 240),
    ktc_value_snapshot = sample(2000:9000, n),
    target_ppg_share = runif(n, 0.1, 1.5)
  )
  models <- fit_quantile_models(train, target = "target_ppg_share")

  # Newdata with all features NA — must fall back to empirical
  miss <- tibble::tibble(
    position = "WR", pick = NA_real_, ras = NA_real_, forty = NA_real_,
    vertical = NA_real_, weight = NA_real_, ktc_value_snapshot = NA_real_
  )
  out <- predict_quantile_projection(models, miss)
  expect_equal(out$floor, models$WR$empirical$floor)
  expect_equal(out$median, models$WR$empirical$median)
  expect_equal(out$ceiling, models$WR$empirical$ceiling)
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: failures.

- [ ] **Step 3: Implement projection_model.R**

Create `analysis/fantasy_sharpe/R/projection_model.R`:

```r
# analysis/fantasy_sharpe/R/projection_model.R
# Per-position quantile regression at tau = {0.10, 0.50, 0.90} for fantasy outcomes.
# Mirrors R/grader_projection.R from the original draft-sharpe-analysis repo.

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(quantreg)
})
source(here::here("analysis/fantasy_sharpe/R/constants.R"))

PROJECTION_TAUS <- c(floor = 0.10, median = 0.50, ceiling = 0.90)
PROJECTION_FEATURE_COLS <- c("pick", "ras", "forty", "vertical",
                             "weight", "ktc_value_snapshot")

assemble_features <- function(draft, ngs, ktc_snapshot) {
  draft |>
    dplyr::transmute(
      rookie_year = season, pfr_player_name, position, pick,
      gsis_id = if ("gsis_id" %in% names(draft)) gsis_id else NA_character_
    ) |>
    dplyr::left_join(
      ngs |>
        dplyr::transmute(rookie_year = draft_year, pfr_player_name = player_name,
                         position = pos, ras, forty, vertical, broad_jump, weight, height),
      by = c("rookie_year", "pfr_player_name", "position")
    ) |>
    dplyr::left_join(
      ktc_snapshot |> dplyr::select(pfr_player_name, ktc_value_snapshot),
      by = "pfr_player_name"
    )
}

# Fit three quantile regressions (tau = 0.10, 0.50, 0.90) per position.
# Also stores empirical positional quantiles as a fallback for prospects whose
# features are NA at predict time. Returns:
#   list[position] = list(
#     fits = list(q10 = rq_or_null, q50 = ..., q90 = ...),
#     empirical = list(floor = num, median = num, ceiling = num),
#     n = integer
#   )
fit_quantile_models <- function(features_with_target, target,
                                feature_cols = PROJECTION_FEATURE_COLS,
                                taus = PROJECTION_TAUS) {
  positions <- unique(features_with_target$position)
  out <- vector("list", length(positions))
  names(out) <- positions

  formula_str <- paste(target, "~", paste(c("log(pick + 1)", setdiff(feature_cols, "pick")),
                                          collapse = " + "))
  fml <- stats::as.formula(formula_str)

  for (pos in positions) {
    sub <- features_with_target |>
      dplyr::filter(position == !!pos) |>
      dplyr::select(dplyr::all_of(c(feature_cols, target))) |>
      tidyr::drop_na()
    pos_all <- features_with_target |>
      dplyr::filter(position == !!pos) |>
      dplyr::pull(.data[[target]])
    empirical <- list(
      floor   = stats::quantile(pos_all, taus[["floor"]], na.rm = TRUE) |> unname(),
      median  = stats::quantile(pos_all, taus[["median"]], na.rm = TRUE) |> unname(),
      ceiling = stats::quantile(pos_all, taus[["ceiling"]], na.rm = TRUE) |> unname()
    )

    fits <- list(q10 = NULL, q50 = NULL, q90 = NULL)
    if (nrow(sub) >= 8) {
      for (q_name in names(taus)) {
        tau_val <- taus[[q_name]]
        slot <- sprintf("q%02d", round(tau_val * 100))
        fits[[slot]] <- tryCatch(
          quantreg::rq(fml, tau = tau_val, data = sub),
          error = function(e) NULL
        )
      }
    }

    out[[pos]] <- list(fits = fits, empirical = empirical, n = nrow(sub))
  }
  out
}

# Predict floor / median / ceiling per row of newdata. Falls back to empirical
# positional quantiles when feature cols are NA or the rq fit is unavailable.
# Monotonizes so floor <= median <= ceiling.
predict_quantile_projection <- function(models, newdata,
                                        feature_cols = PROJECTION_FEATURE_COLS) {
  out <- newdata |>
    dplyr::mutate(floor = NA_real_, median = NA_real_, ceiling = NA_real_)

  for (i in seq_len(nrow(out))) {
    pos <- out$position[i]
    m <- models[[pos]]
    if (is.null(m)) next

    row <- out[i, feature_cols, drop = FALSE]
    has_features <- !any(is.na(row))
    fits_ok <- !is.null(m$fits$q10) && !is.null(m$fits$q50) && !is.null(m$fits$q90)

    if (has_features && fits_ok) {
      f_pred <- as.numeric(stats::predict(m$fits$q10, newdata = row))
      m_pred <- as.numeric(stats::predict(m$fits$q50, newdata = row))
      c_pred <- as.numeric(stats::predict(m$fits$q90, newdata = row))
    } else {
      f_pred <- m$empirical$floor
      m_pred <- m$empirical$median
      c_pred <- m$empirical$ceiling
    }

    # Monotonize (rare crossings can occur with small samples)
    sorted <- sort(c(f_pred, m_pred, c_pred))
    out$floor[i]   <- sorted[1]
    out$median[i]  <- sorted[2]
    out$ceiling[i] <- sorted[3]
  }
  out
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: all 4 projection_model tests pass.

- [ ] **Step 5: Commit**

```bash
git add analysis/fantasy_sharpe/R/projection_model.R \
        analysis/fantasy_sharpe/tests/testthat/test-projection-model.R
git commit -m "feat(fantasy_sharpe): quantile-regression projection (floor/median/ceiling)"
```

### Task 6.2: Wire projection into the pipeline

**Files:**
- Modify: `analysis/fantasy_sharpe/data_pipeline.R`

- [ ] **Step 1: Append projection block to data_pipeline.R**

After the player_frame is computed, before final writes, append:

```r
cat("[fantasy_sharpe] Fitting projection models...\n")

source(here("analysis/fantasy_sharpe/R/projection_model.R"))

ngs <- load_ngs_features(c(ELIGIBILITY_COHORTS, 2026))

# Training features: assemble for the eligibility cohorts.
train_features <- assemble_features(
  draft = draft,
  ngs = ngs,
  ktc_snapshot = rookies |>
    dplyr::filter(season %in% ELIGIBILITY_COHORTS) |>
    dplyr::select(pfr_player_name, ktc_value_snapshot)
) |>
  dplyr::left_join(
    player_frame |> dplyr::select(pfr_player_name, ppg_share, peak_ktc),
    by = "pfr_player_name"
  )

# Fit per-position quantile-regression models for each target.
models_share <- fit_quantile_models(
  train_features |> dplyr::rename(target_ppg_share = ppg_share),
  target = "target_ppg_share"
)
models_ktc <- fit_quantile_models(
  train_features |> dplyr::rename(target_peak_ktc = peak_ktc),
  target = "target_peak_ktc"
)

# 2026 rookie features.
draft_2026 <- load_draft_picks_for(2026)
ktc_2026 <- ktc_now |>
  dplyr::filter(is_rookie == TRUE) |>
  dplyr::transmute(pfr_player_name = name, ktc_value_snapshot = ktc_value)
features_2026 <- assemble_features(draft_2026, ngs, ktc_2026)

share_preds <- predict_quantile_projection(models_share, features_2026) |>
  dplyr::transmute(ppg_share_floor = floor,
                   ppg_share_median = median,
                   ppg_share_ceiling = ceiling)
ktc_preds <- predict_quantile_projection(models_ktc, features_2026) |>
  dplyr::transmute(peak_ktc_floor = floor,
                   peak_ktc_median = median,
                   peak_ktc_ceiling = ceiling)

predictions_2026 <- features_2026 |>
  dplyr::bind_cols(share_preds) |>
  dplyr::bind_cols(ktc_preds)

# Flatten quantile-regression coefficients for downstream inspection.
flatten_models <- function(models, target_label) {
  purrr::imap_dfr(models, \(m, pos) {
    rows <- list()
    for (q_name in names(m$fits)) {
      f <- m$fits[[q_name]]
      if (is.null(f)) next
      coefs <- stats::coef(f)
      rows[[q_name]] <- tibble::tibble(
        target = target_label, position = pos, tau = q_name,
        feature = names(coefs), coefficient = as.numeric(coefs),
        n = m$n
      )
    }
    dplyr::bind_rows(rows)
  })
}
model_coefs <- dplyr::bind_rows(
  flatten_models(models_share, "ppg_share"),
  flatten_models(models_ktc, "peak_ktc")
)

projection_payload <- list(
  predictions = predictions_2026,
  coefficients = model_coefs
)

arrow::write_parquet(predictions_2026,
  here("analysis/fantasy_sharpe/data/projection_model.parquet"))
arrow::write_parquet(model_coefs,
  here("analysis/fantasy_sharpe/data/projection_coefficients.parquet"))

cat("[fantasy_sharpe] Wrote", nrow(predictions_2026), "2026 predictions.\n")
```

- [ ] **Step 2: Run pipeline**

```bash
Rscript analysis/fantasy_sharpe/data_pipeline.R
```

Expected: pipeline runs through; 2 new parquet files written.

- [ ] **Step 3: Verify**

```bash
python3 -c "
import pandas as pd
p = pd.read_parquet('analysis/fantasy_sharpe/data/projection_model.parquet')
print(p[['pfr_player_name','position','pick','predicted_ppg_share','ppg_share_pi_lo','ppg_share_pi_hi','predicted_peak_ktc']].head(15))
"
```

Expected: 2026 rookies with non-NA predictions for those with NGS + KTC features.

- [ ] **Step 4: Commit**

```bash
git add analysis/fantasy_sharpe/data_pipeline.R
git commit -m "feat(fantasy_sharpe): wire projection model into pipeline"
```

---

## Phase 7: Article (analysis.Rmd)

### Task 7.1: Article skeleton + sections 1-2

**Files:**
- Create: `analysis/fantasy_sharpe/analysis.Rmd`

- [ ] **Step 1: Write article skeleton**

Create `analysis/fantasy_sharpe/analysis.Rmd`:

```rmd
---
title: "Fantasy Dynasty Sharpe — Positional Value, Indexed by ADP"
author: "Nick"
date: "`r Sys.Date()`"
output:
  html_document:
    self_contained: true
    toc: true
    toc_float: true
    theme: cosmo
    code_folding: hide
knit: (function(input, ...) rmarkdown::render(input, output_dir = dirname(input)))
---

```{r setup, include=FALSE}
knitr::opts_chunk$set(echo = FALSE, warning = FALSE, message = FALSE,
                      fig.path = "charts/", dpi = 150, fig.width = 9, fig.height = 5.5)
library(here)
library(dplyr)
library(ggplot2)
library(arrow)
library(scales)

player_frame <- read_parquet(here("analysis/fantasy_sharpe/data/fantasy_sharpe.parquet"))
tier_frame   <- read_parquet(here("analysis/fantasy_sharpe/data/tier_sharpe.parquet"))
predictions  <- read_parquet(here("analysis/fantasy_sharpe/data/projection_model.parquet"))
coefs        <- read_parquet(here("analysis/fantasy_sharpe/data/projection_coefficients.parquet"))
```

# Why position-adjusted PPG and KTC value, not raw fantasy points

[1-2 paragraphs explaining the framing — production share normalizes across position
and era; asset value captures the dynasty-trade-flippability that production alone misses.]

# Headline: two parallel Sharpes

For every dynasty rookie cohort 2020-2022, we compute two parallel Sharpes per
(position × tier):

- **Production Sharpe** — return = 4-yr position-adjusted PPG share, replacement = worst-startable share.
- **Asset Sharpe** — return = peak KTC value during years 1-4, replacement = KTC value of QB24/RB24/WR36/TE12.

```{r sharpe-grid, fig.cap = "Sharpe by tier × position, both sharpe kinds (rookie ADP analysis)."}
tier_frame |>
  filter(analysis == "rookie_adp") |>
  ggplot(aes(x = tier, y = sharpe_linear, fill = sharpe_kind)) +
  geom_col(position = "dodge") +
  facet_wrap(~ position) +
  labs(x = NULL, y = "Sharpe (linear)", fill = "Kind") +
  theme_minimal(base_size = 12) +
  theme(axis.text.x = element_text(angle = 35, hjust = 1))
```
```

- [ ] **Step 2: Render**

```bash
cd /Users/nick/projects/dynasty-dashboard
Rscript -e 'rmarkdown::render("analysis/fantasy_sharpe/analysis.Rmd")'
```

Expected: writes `analysis/fantasy_sharpe/analysis.html` with the headline chart + figures under `charts/`.

- [ ] **Step 3: Commit**

```bash
git add analysis/fantasy_sharpe/analysis.Rmd analysis/fantasy_sharpe/charts/
git commit -m "feat(fantasy_sharpe): article skeleton with headline Sharpe grid"
```

### Task 7.2: Article sections 3-5 (startup ADP, divergence, positional patterns)

**Files:**
- Modify: `analysis/fantasy_sharpe/analysis.Rmd` (append)

- [ ] **Step 1: Append sections**

Append to `analysis.Rmd`:

```rmd
# Startup ADP

[Same chart structure as rookie ADP, with `analysis == "startup_adp"`.]

```{r startup-grid}
tier_frame |>
  filter(analysis == "startup_adp") |>
  ggplot(aes(x = tier, y = sharpe_linear, fill = sharpe_kind)) +
  geom_col(position = "dodge") +
  facet_wrap(~ position) +
  labs(x = NULL, y = "Sharpe (linear) — startup ADP") +
  theme_minimal(base_size = 12) +
  theme(axis.text.x = element_text(angle = 35, hjust = 1))
```

# Production vs Asset divergence

Players with high production but low asset value (and vice versa).

```{r divergence-table}
player_frame |>
  filter(!is.na(ppg_share), !is.na(peak_ktc)) |>
  mutate(
    prod_z = (ppg_share - mean(ppg_share, na.rm = TRUE)) / sd(ppg_share, na.rm = TRUE),
    asset_z = (peak_ktc - mean(peak_ktc, na.rm = TRUE)) / sd(peak_ktc, na.rm = TRUE),
    divergence = prod_z - asset_z
  ) |>
  arrange(desc(abs(divergence))) |>
  select(pfr_player_name, position, season, ppg_share, peak_ktc, divergence) |>
  head(15) |>
  knitr::kable(digits = 2)
```

# Positional value patterns

[1-2 paragraphs of narrative tying the chart back to dynasty drafting intuition.]
```

- [ ] **Step 2: Render**

```bash
Rscript -e 'rmarkdown::render("analysis/fantasy_sharpe/analysis.Rmd")'
```

- [ ] **Step 3: Commit**

```bash
git add analysis/fantasy_sharpe/analysis.Rmd analysis/fantasy_sharpe/charts/
git commit -m "feat(fantasy_sharpe): article sections — startup, divergence, patterns"
```

### Task 7.3: Article sections 6-7 (projection coefficients + caveats)

**Files:**
- Modify: `analysis/fantasy_sharpe/analysis.Rmd`

- [ ] **Step 1: Append**

```rmd
# Projection model coefficients

The counter-analysis projection uses NGS combine metrics, `log(pick + 1)` for NFL
draft pick, and at-snapshot KTC value as features. Per-position quantile regression
at τ ∈ {0.10, 0.50, 0.90} produces floor / median / ceiling outcomes — better suited
than symmetric Gaussian intervals for the skewed distribution of fantasy outcomes.

```{r coefs-table}
coefs |>
  filter(feature != "(Intercept)") |>
  mutate(coefficient = round(coefficient, 4)) |>
  tidyr::pivot_wider(
    id_cols = c(position, target, feature),
    names_from = tau,
    values_from = coefficient,
    names_prefix = "tau_"
  ) |>
  knitr::kable()
```

# Caveats

- **KTC ≠ true ADP.** Tier definitions derived from KTC ranks may diverge from
  real rookie/startup ADP at the margins. v2 will swap to true ADP from a
  Sleeper aggregator or Dynasty Data Lab once accessible.
- **Small training sample.** 3 cohorts (~30-50 fantasy-relevant rookies per
  position) make coefficients directional rather than authoritative.
- **Superflex bias in KTC values.** Asset Sharpe leans on KTC superflex value;
  1QB-league readers should weight Production Sharpe more.
```

- [ ] **Step 2: Render**

```bash
Rscript -e 'rmarkdown::render("analysis/fantasy_sharpe/analysis.Rmd")'
```

- [ ] **Step 3: Commit**

```bash
git add analysis/fantasy_sharpe/analysis.Rmd analysis/fantasy_sharpe/analysis.html analysis/fantasy_sharpe/charts/
git commit -m "feat(fantasy_sharpe): article complete with projection + caveats"
```

---

## Phase 8: Streamlit projection view

### Task 8.1: Build a fixture parquet

**Files:**
- Create: `tests/fixtures/fantasy_sharpe_projection_fixture.parquet`
- Create: `tests/conftest_fantasy_sharpe.py` (helper to build it)

- [ ] **Step 1: Build a small fixture**

Create `tests/fixtures/fantasy_sharpe_projection_fixture.parquet` via a one-shot script. Run from `dynasty-dashboard/`:

```bash
python3 -c "
import pandas as pd
df = pd.DataFrame([
    dict(pfr_player_name='Cam Skattebo', position='RB', team='NYG', pick=27,
         ktc_value_snapshot=6500,
         ppg_share_floor=0.42, ppg_share_median=0.85, ppg_share_ceiling=1.28,
         peak_ktc_floor=5800, peak_ktc_median=7900, peak_ktc_ceiling=10000),
    dict(pfr_player_name='Tetairoa McMillan', position='WR', team='CAR', pick=5,
         ktc_value_snapshot=8100,
         ppg_share_floor=0.62, ppg_share_median=1.05, ppg_share_ceiling=1.48,
         peak_ktc_floor=7100, peak_ktc_median=9100, peak_ktc_ceiling=11100),
])
df.to_parquet('tests/fixtures/fantasy_sharpe_projection_fixture.parquet')
print('wrote fixture')
"
```

- [ ] **Step 2: Commit**

```bash
mkdir -p tests/fixtures
git add tests/fixtures/fantasy_sharpe_projection_fixture.parquet
git commit -m "test(fantasy_sharpe): fixture parquet for view tests"
```

### Task 8.2: View smoke test

**Files:**
- Create: `tests/test_fantasy_sharpe_projection.py`

- [ ] **Step 1: Write the failing test**

```python
"""Smoke + schema tests for views/fantasy_sharpe_projection.py."""
from pathlib import Path
import pandas as pd
import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "fantasy_sharpe_projection_fixture.parquet"


def test_fixture_has_required_columns():
    df = pd.read_parquet(FIXTURE)
    required = {
        "pfr_player_name", "position", "team", "pick",
        "ktc_value_snapshot",
        "ppg_share_floor", "ppg_share_median", "ppg_share_ceiling",
        "peak_ktc_floor", "peak_ktc_median", "peak_ktc_ceiling",
    }
    assert required.issubset(df.columns)


def test_view_imports_cleanly():
    import importlib
    mod = importlib.import_module("views.fantasy_sharpe_projection")
    assert hasattr(mod, "render")


def test_view_render_with_fixture(monkeypatch):
    """Render must run without raising against the fixture parquet."""
    import importlib
    from unittest.mock import MagicMock

    # Stub Streamlit calls we care about. Real Streamlit isn't available in pytest.
    fake_st = MagicMock()
    monkeypatch.setattr("views.fantasy_sharpe_projection.st", fake_st, raising=False)
    monkeypatch.setenv("FANTASY_SHARPE_PROJECTION_FIXTURE", str(FIXTURE))

    mod = importlib.import_module("views.fantasy_sharpe_projection")
    mod.render()
    # Sanity: the mock was used (the view called at least one streamlit primitive)
    assert fake_st.method_calls, "render() did not invoke any streamlit calls"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_fantasy_sharpe_projection.py -v
```

Expected: failure on import (file doesn't exist).

### Task 8.3: Implement the view

**Files:**
- Create: `views/fantasy_sharpe_projection.py`

- [ ] **Step 1: Write the view**

Create `views/fantasy_sharpe_projection.py`:

```python
"""Streamlit view: per-rookie fantasy Sharpe projections for the current cohort."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARQUET = REPO_ROOT / "analysis" / "fantasy_sharpe" / "data" / "projection_model.parquet"


def _load_predictions() -> pd.DataFrame:
    fixture = os.environ.get("FANTASY_SHARPE_PROJECTION_FIXTURE")
    path = Path(fixture) if fixture else DEFAULT_PARQUET
    if not path.exists():
        st.error(
            f"Projections parquet not found at {path}. "
            "Run `Rscript analysis/fantasy_sharpe/data_pipeline.R` first."
        )
        return pd.DataFrame()
    return pd.read_parquet(path)


def render() -> None:
    st.title("Rookie Projections")
    st.caption(
        "Per-rookie fantasy Sharpe projections for the current cohort. "
        "Production Sharpe = win-now lens (PPG share). Asset Sharpe = rebuild lens (KTC value)."
    )

    df = _load_predictions()
    if df.empty:
        return

    with st.sidebar:
        st.header("Filters")
        position_filter = st.multiselect(
            "Position",
            options=sorted(df["position"].dropna().unique()),
            default=sorted(df["position"].dropna().unique()),
        )

    view = df[df["position"].isin(position_filter)].copy()

    view = view.sort_values("ppg_share_median", ascending=False, na_position="last")

    cols_to_show = [
        "pfr_player_name", "position", "team", "pick",
        "ktc_value_snapshot",
        "ppg_share_floor", "ppg_share_median", "ppg_share_ceiling",
        "peak_ktc_floor", "peak_ktc_median", "peak_ktc_ceiling",
    ]
    available = [c for c in cols_to_show if c in view.columns]
    st.dataframe(
        view[available].rename(columns={
            "pfr_player_name": "Player",
            "position": "Pos",
            "team": "Team",
            "pick": "NFL Pick",
            "ktc_value_snapshot": "KTC (post-draft)",
            "ppg_share_floor": "PPG share — Floor (q10)",
            "ppg_share_median": "PPG share — Median",
            "ppg_share_ceiling": "PPG share — Ceiling (q90)",
            "peak_ktc_floor": "Peak KTC — Floor",
            "peak_ktc_median": "Peak KTC — Median",
            "peak_ktc_ceiling": "Peak KTC — Ceiling",
        }),
        use_container_width=True,
    )
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
pytest tests/test_fantasy_sharpe_projection.py -v
```

Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add views/fantasy_sharpe_projection.py tests/test_fantasy_sharpe_projection.py
git commit -m "feat(fantasy_sharpe): Streamlit projection view with smoke tests"
```

### Task 8.4: Register the view in the sidebar

**Files:**
- Modify: `components/sidebar.py`
- Modify: `streamlit_app.py`

- [ ] **Step 1: Inspect sidebar**

```bash
grep -n "tools\|menu\|select" components/sidebar.py | head -20
```

Find the existing tool list (e.g., `TOOLS = ["Ranking Comparison", ...]` or similar).

- [ ] **Step 2: Add "Rookie Projections" entry**

Edit `components/sidebar.py` to add `"Rookie Projections"` to the tool options list (alongside `"Draft Wizard"`, `"Trade History"`, etc.).

- [ ] **Step 3: Add a route block in streamlit_app.py**

In `streamlit_app.py` after the existing `elif selected_tool == ...` chain, add:

```python
    elif selected_tool == "Rookie Projections":
        from views.fantasy_sharpe_projection import render
        render()
```

- [ ] **Step 4: Manual smoke**

```bash
streamlit run streamlit_app.py
```

Open the app, select "Rookie Projections" in the sidebar (after connecting a league), and verify the table renders.

- [ ] **Step 5: Commit**

```bash
git add components/sidebar.py streamlit_app.py
git commit -m "feat(fantasy_sharpe): register Rookie Projections in sidebar"
```

---

## Phase 9: End-to-end validation

### Task 9.1: Run the full pipeline + render + view test

**Files:** none (validation only)

- [ ] **Step 1: Run pipeline**

```bash
cd /Users/nick/projects/dynasty-dashboard
Rscript analysis/fantasy_sharpe/data_pipeline.R
```

- [ ] **Step 2: Run all R tests**

```bash
Rscript analysis/fantasy_sharpe/tests/testthat.R
```

Expected: all green.

- [ ] **Step 3: Run all Python tests**

```bash
pytest tests/ -v
```

Expected: all green.

- [ ] **Step 4: Render the article**

```bash
Rscript -e 'rmarkdown::render("analysis/fantasy_sharpe/analysis.Rmd")'
```

Expected: `analysis/fantasy_sharpe/analysis.html` is updated. Open it in a browser, scroll through, and verify:
- Headline grid renders with both Sharpe kinds
- Startup grid renders
- Divergence table has plausible names
- Coefficients table is non-empty
- Caveats section is present

- [ ] **Step 5: Commit final article HTML**

```bash
git add analysis/fantasy_sharpe/analysis.html analysis/fantasy_sharpe/charts/
git commit -m "docs(fantasy_sharpe): final rendered article"
```

---

## Self-review notes

**Spec coverage:**
- Article + Streamlit tool — Phase 7 + Phase 8.
- Two parallel Sharpes (Production + Asset) — Phase 4.
- Position-adjusted return — `compute_player_production_share` in Task 4.1.
- Hit threshold 0.67 — `HIT_THRESHOLD_SHARE` in Task 1.1.
- Replacement at QB24/RB24/WR36/TE12 — `REPLACEMENT_RANK` in Task 1.1.
- KTC refresh post-NFL-draft — Phase 2.
- NGS + draft + KTC projection model — Phase 6.
- Quantile-regression floor/median/ceiling — Task 6.1, surfaced in view at Task 8.3 as columns `ppg_share_{floor,median,ceiling}` and `peak_ktc_{floor,median,ceiling}`.
- Rookie ADP and Startup ADP both — Tasks 5.1 (rookie) and 5.2 (startup).
- Schema + formula tests — Phases 1, 3, 4, 6, 8.

**Known caveats baked in (not bugs):**
- Replacement KTC by season uses the *current* KTC snapshot's rank-N value as a proxy across all historical seasons. A true historical version would compute rank-N at each historical date. Called out in spec "Risks" and surfaced in the article caveats. v2 work.
- Player-ID joins between nflreadr (gsis_id, pfr_player_name) and KTC (mfl_id, name) rely on `nflreadr::load_ff_playerids()`. Some 2026 rookies may miss the join until ff_playerids gets refreshed; the pipeline silently drops unmatched rookies. The startup-task verification step explicitly checks the matched count.
