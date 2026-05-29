# Draft App Upgrades — Design

**Date:** 2026-05-29
**Goal:** Get the dynasty dashboard ready to use live on a phone during the upcoming
2026 rookie draft: add NFL draft capital as a ranking source, fold it into an
equal-weight blend, surface where the sources disagree, make the Draft Wizard
usable on a phone, improve the refresh/freshness UX, and deploy to Streamlit Cloud.

## Context

- Streamlit app, manual page dispatch (`views/`), `uv` for deps, Python 3.12.
- Rookie rankings today come from LateRound (manual CSV), FantasyCalc (API), KTC
  (scrape). `views/draft_wizard.py::_get_rookies()` merges them and computes a
  weighted `blended_rank` (default 50/25/25).
- `data/` is **gitignored** → a Streamlit Cloud clone starts empty; the KTC scrape
  may be blocked from cloud IPs. App needs **no secrets** (all sources keyless).
- 2026 NFL draft data confirmed available from nflverse (`draft_picks.parquet`,
  season 2026, 80 skill players; names match our rookie set).

## Components

### 1. NFL Draft Capital source — `ingestion/nfl_draft.py`
- `fetch_nfl_draft(season=CURRENT_SEASON) -> pd.DataFrame`
  - Download nflverse `draft_picks.parquet` via `requests` → `BytesIO` →
    `pd.read_parquet` (avoid fsspec URL dependency for cloud portability).
  - Filter `season == season` and `position in {QB,RB,WR,TE}`.
  - Columns out: `name` (from `pfr_player_name`), `position`, `team`, `college`,
    `draft_overall_pick` (= `pick`), `draft_skill_rank`, `draft_pos_rank`.
  - `draft_skill_rank`: dense rank of skill players by `pick` (1,2,3…).
  - `draft_pos_rank`: rank by `pick` within position (WR1, WR2…).
  - On empty/failure: return empty DataFrame (blend degrades gracefully).
- `merge_nfl_draft(rookies, draft) -> rookies` — name+position normalized join
  with fuzzy fallback, mirroring `ingestion/lateround.py::merge_lateround`.
- Persisted to `data/nfl_draft.parquet` (+ seed copy).

### 2. Equal-weight blend (in `_get_rookies`)
- `RANK_SOURCES` gains `"NFL Draft": "draft_skill_rank"`.
- Per-source rookie ranks used in the blend: `lr_rank`, `fc_rookie_rank`,
  `ktc_rookie_rank`, `draft_skill_rank`.
- `blended_rank` = mean of available source ranks with **equal default weights
  (0.25 each)**, renormalized over present sources (a player missing a source —
  e.g. a UDFA with no draft rank — blends over the rest). Sidebar weight sliders
  default to 25/25/25/25 and remain adjustable.

### 3. Disagreement surfacing (in `_get_rookies` + board)
- Compute over the per-source rookie ranks (need ≥2 present):
  - `rank_spread` = max − min across sources.
  - `source_high` = most bullish source (min rank), `source_low` = most bearish.
- Draft Board: add sortable **Spread** column.
- New **Biggest Disagreements** section (below the board tabs): table sorted by
  `rank_spread` desc showing each rookie's LR / FC / KTC / Draft ranks, the range,
  and a "X loves / Y fades" label.

### 4. Mobile Draft Wizard (`views/draft_wizard.py`)
- Move the most-used live controls into the **top of the main pane**: **Rank by**
  selector and the board position filter (today they live in the sidebar drawer).
- **Compact default board**: Player · Pos · Team · Blend# · Draft# · Spread, with
  full per-source ranks/values behind an expander ("Show all source ranks").
- **Age as decimal** (e.g. 22.3) wherever rookie age shows.
- Mock-draft grid: reduce `st.columns(min(num_teams, 6))` → fewer columns so it
  fits a phone (low priority; live "best available" flow is the draft-day path).
- Blend-weight sliders stay in the sidebar (advanced).

### 5. Refresh + freshness (`components/sidebar.py`, `tools/refresh_rankings.py`)
- Sidebar **Data** section shows per-source freshness: FantasyCalc, KTC, LateRound,
  NFL Draft — each with player count + last-updated age.
- One "Refresh Data" button (already one-tap) now also fetches NFL draft capital.
- **Seed fallback**: if a live fetch fails (KTC blocked in cloud), keep the
  existing/seed file and warn rather than wiping data.

### 6. Deploy to Streamlit Cloud
- Commit fresh snapshots to **`data/seed/`** (un-gitignore that dir):
  `fantasycalc.parquet`, `ktc.parquet`, `merged.parquet`, `nfl_draft.parquet`,
  `lateround_rankings.csv`.
- **Bootstrap on startup**: if `data/*.parquet` is missing (fresh cloud clone),
  copy from `data/seed/`. Small helper called from `streamlit_app.py`.
- Add `.streamlit/config.toml` (theme + `[server] headless`).
- Generate `requirements.txt` from deps (Streamlit Cloud reliability).
- Streamlit Cloud: repo `stranger9977/dynasty-dashboard`, deploy from `main`
  after the `feat/draft-app-upgrades` branch is merged; main file
  `streamlit_app.py`, Python 3.12. No secrets.

## Data flow

refresh → `fetch_fantasycalc` + `fetch_ktc` + `fetch_nfl_draft` → parquets →
`merge_rankings` (FC+KTC, all players) → `merged.parquet`. At render,
`_get_rookies()` filters rookies, merges LateRound + NFL Draft, computes per-source
rookie ranks, equal-weight `blended_rank`, and `rank_spread`/`source_high/low`.

## Error handling
- Each live fetch wrapped; failure → fall back to existing parquet/seed + sidebar
  warning. App never crashes to an empty state if a seed exists.
- Missing source for a player → excluded from that player's blend (renormalized);
  spread computed only when ≥2 sources present.

## Testing
- Unit: `draft_skill_rank`/`draft_pos_rank` dense-ranking; `merge_nfl_draft`
  name+position join (incl. a suffix case like "Omar Cooper Jr.").
- Unit: equal-weight blend with a missing source renormalizes correctly.
- Headless (AppTest, like `/tmp/verify_app.py`): app boots, Draft Wizard returns
  rookies with `draft_skill_rank`, `rank_spread`, `blended_rank` populated.
- Manual: run the app, view board + Biggest Disagreements, run one mock pick on a
  narrow viewport.

## Out of scope (YAGNI)
- Persisting Sleeper login across cloud sessions / cold starts.
- Live sync with an in-progress Sleeper draft's actual picks.
- Non-skill positions in draft capital; historical draft classes.
- Reworking the all-players views (Ranking Comparison, etc.) — disagreement work is
  rookie-scoped since draft capital only exists for the current class.
