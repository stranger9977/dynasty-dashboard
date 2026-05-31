# Roster Projection Impact — Design (Phase B)

**Date:** 2026-05-30
**Status:** Approved for planning
**Scope:** Phase B of the Draft Wizard expansion. Adds 2026 season projections and a new
**"Roster Impact"** tab showing, per manager, the projected points their rookie-draft haul
adds to the roster — total, and the marginal upgrade to their starting lineup. Phase A
(Draft Value Recap) already shipped.

---

## Goal

Quantify each manager's rookie draft in **projected fantasy points**: how many points they
added, and how many of those points actually improve their *starting* lineup (a rookie that
can't crack a veteran lineup adds ~0).

## The data source (de-risked)

Sleeper publishes **full-season 2026 projections** at:

```
https://api.sleeper.com/projections/nfl/2026?season_type=regular
```

Verified 2026-05-30: 9,384 rows, **810 skill players** with a non-null `pts_ppr`
(QB 76 / RB 138 / WR 219 / TE 127), including all drafted 2026 rookies (e.g. Jeremiyah Love
239, Mendoza 212, Tate 190). Each row has:

- a **top-level `player_id`** = the **Sleeper player id** — the SAME id used in
  `get_rosters()` (`players`) and in live draft picks (`player_id`).
- `stats.pts_ppr`, `stats.pts_half_ppr`, `stats.pts_std`.
- a `player` object (`first_name`, `last_name`, `position`, `team`, `years_exp`).

**Why this matters:** rosters, draft picks, and projections all key on one Sleeper id, so the
merge is a **dictionary join on `player_id` — lossless, no fuzzy matching, no dropped
names.** This directly satisfies the "merge correctly / don't lose important names"
requirement: any rostered player Sleeper projects is matched exactly; a player with no match
is genuinely unprojected (UDFA/practice-squad), and we surface a coverage count so nothing is
silently missing.

League scoring is full PPR (`config.PPR = 1`) → default `pts_ppr`, with a Half/Standard
toggle (all three are in the payload). TE-premium is out of scope for v1 (a possible later
refinement; `pts_ppr` is the honest PPR baseline).

## Non-goals (Phase B)

- No TE-premium or custom league-scoring recomputation from raw stat lines.
- No projections beyond the season-long total (no weekly modeling).
- No changes to Phase A (Draft Recap) behavior.

---

## Architecture

Mirrors the existing fetch/load + seed + refresh patterns (`ingestion/nfl_draft.py`,
`ingestion/seed.py`, `components/sidebar.py`).

### `ingestion/projections.py` — fetch/parse/load

```python
PROJECTIONS_URL = "https://api.sleeper.com/projections/nfl/{season}?season_type=regular"
SKILL = ["QB", "RB", "WR", "TE"]
OUT_COLS = ["player_id", "name", "position", "team",
            "pts_ppr", "pts_half_ppr", "pts_std", "years_exp"]

def _parse_projections(raw: list) -> pd.DataFrame:
    """Sleeper season rows -> tidy skill-player frame. Keeps QB/RB/WR/TE with a
    non-null pts_ppr; player_id is the Sleeper id (str). Sorted by pts_ppr desc."""
    # build rows from it["player_id"], it["player"], it["stats"]; filter; DataFrame(OUT_COLS)

def fetch_projections(season: int = CURRENT_SEASON) -> pd.DataFrame:
    """GET the URL, return _parse_projections(resp.json())."""

def load_projections() -> pd.DataFrame:
    """Read PROJECTIONS_PARQUET, or empty DataFrame(columns=OUT_COLS) if absent."""
```

`_parse_projections` is pure and unit-tested on sample rows; `fetch_projections` is the thin
network wrapper (same split as `nfl_draft._compute_draft_ranks` / `fetch_nfl_draft`).

### `ingestion/roster_impact.py` — pure lineup math

```python
def starter_points(players: pd.DataFrame, counts=None, score_col="pts") -> float:
    """Sum of each position's top-N projections (the starting-lineup baseline).
    players: DataFrame with 'position' and score_col. counts defaults to STARTER_COUNTS."""

def points_above_starters(baseline: pd.DataFrame, added: pd.DataFrame,
                          counts=None, score_col="pts") -> float:
    """Marginal lineup upgrade = starter_points(baseline+added) − starter_points(baseline).
    A rookie that can't beat the worst starter at its position contributes 0; multiple
    rookies at one position displace multiple starters correctly."""
```

`STARTER_COUNTS = {"QB": 2, "RB": 3, "WR": 4, "TE": 2}` (the user's lineup definition) lives in
`config.py`.

### `views/roster_impact.py` — the tab

`render_roster_impact(rookies, draft, league_id)`:

1. `load_projections()`; if empty → `st.info("No 2026 projections loaded — Refresh Data")`.
2. **Scoring toggle** (PPR default / Half / Standard) → `score_col`.
3. **Drafted rookies per manager** (`_collect_drafted`): live Sleeper draft preferred —
   `get_draft_picks(draft_id)`, `manager = build_roster_to_manager()[roster_id]`,
   `player_id = pick["player_id"]`. Mock fallback — `st.session_state["draft_picks"]`, mapping
   each pick's `player` name → `sleeper_id` via the `rookies` frame. If none → info + return.
4. **Baseline rosters:** `get_rosters(league_id)` → `{manager: set(player_id)}`. For each
   manager, `baseline_ids = roster_ids − drafted_ids` (subtract the draft picks so we never
   double-count if Sleeper has already added them to the roster).
5. Look projections up by `player_id` (`proj.set_index("player_id")`); unmatched ids drop out.
6. Per manager: `total_added = Σ score_col(drafted)`; `above = points_above_starters(baseline,
   added, STARTER_COUNTS, score_col)`.
7. **Two bar charts** side by side (`st.columns(2)`): Total projected pts added; Pts added
   above starters. Plus a **coverage caption** ("X/Y rostered players matched a projection")
   and a **per-manager expander** breakdown (each rookie: name, pos, projected pts).

### Wiring & plumbing

- **`views/draft_wizard.py`** `render()`: 4th tab `"Roster Impact"` →
  `render_roster_impact(rookies, draft, st.session_state.get("league_id", ""))`.
- **`config.py`**: `PROJECTIONS_PARQUET = DATA_DIR / "projections.parquet"`; `STARTER_COUNTS`.
- **`ingestion/seed.py`**: add `"projections.parquet"` to `SEED_FILES` (so the deployed app
  has projections without fetching).
- **`components/sidebar.py`** `_refresh_data()`: fetch projections (try/except like NFL draft),
  write parquet; add a `_fresh(PROJECTIONS_PARQUET, "Projections")` freshness line.
- **`tools/refresh_rankings.py`**: fetch + write projections too (CLI parity).
- Implementation generates `data/projections.parquet` AND commits
  `data/seed/projections.parquet` so the cloud deploy ships with projections.

---

## Testing

- `tests/test_projections.py` (pure): `_parse_projections` on a small sample list —
  keeps QB/RB/WR/TE with non-null `pts_ppr`, drops a K row and a null-`pts_ppr` row,
  `player_id` is a string, `name` joined, columns == `OUT_COLS`, sorted by `pts_ppr` desc.
- `tests/test_roster_impact.py` (pure):
  - `starter_points`: top-N per position summed (e.g. QBs [300,250,200], counts QB:2 → 550);
    multi-position total; fewer players than N sums what exists.
  - `points_above_starters`: a QB 280 over starters [300,250] → +30; a below-cutoff rookie
    (150 vs worst starter 250) → 0; two RBs that both crack the lineup → correct summed delta;
    empty `added` → 0.
- A light AppTest smoke (mock-fallback path) renders the Roster Impact tab without exception.

## Risks / decisions

- **Coverage, not silence:** id-keying can't fuzzy-drop names; the only "misses" are players
  Sleeper doesn't project. The coverage caption makes that explicit.
- **Double-count guard:** `baseline = roster − drafted` keeps the math correct whether the live
  draft is mid-flight (rookies not yet on rosters) or already finalized (rookies added).
- **Superflex:** "top 2 QB" approximates the SF slot via a second QB — consistent with the
  user's stated lineup; not a positional-flex optimizer (out of scope).
- **Seed freshness:** projections shift through the offseason; the sidebar/CLI refresh updates
  the parquet, and re-committing the seed refreshes the deployed copy.
