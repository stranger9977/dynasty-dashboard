# Roster Projection Impact Implementation Plan (Phase B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Roster Impact" tab to the Rookie Draft Wizard that uses Sleeper's 2026 season projections to show, per manager, the projected points their rookie haul adds — total, and the marginal upgrade to their starting lineup.

**Architecture:** A new ingestion module fetches/parses Sleeper season projections (keyed by Sleeper `player_id`, so the merge with rosters/picks is a lossless id-join). A pure lineup-math module computes starter points and the marginal "above starters" delta. A view collects each manager's drafted rookies (live draft, mock fallback), joins projections by id, and renders two bar charts + a per-manager breakdown. Projections are cached to parquet, seeded for cloud, and refreshed via the sidebar/CLI like the other data sources.

**Tech Stack:** Python 3.12, pandas, requests, Streamlit, pytest. Package manager `uv` (`uv run pytest`).

**Spec:** `docs/superpowers/specs/2026-05-30-roster-projection-impact-design.md`

---

## File Structure

- **Create `ingestion/projections.py`** — `_parse_projections` (pure), `fetch_projections`, `load_projections`.
- **Create `ingestion/roster_impact.py`** — pure lineup math: `starter_points`, `points_above_starters`.
- **Create `views/roster_impact.py`** — `_collect_drafted`, `render_roster_impact`.
- **Create `tests/test_projections.py`**, **`tests/test_roster_impact.py`**.
- **Modify `config.py`** — add `PROJECTIONS_PARQUET`, `STARTER_COUNTS`.
- **Modify `ingestion/seed.py`** — add `"projections.parquet"` to `SEED_FILES`.
- **Modify `components/sidebar.py`** — fetch projections in `_refresh_data`; add a freshness line.
- **Modify `tools/refresh_rankings.py`** — fetch + write projections (CLI parity).
- **Modify `views/draft_wizard.py`** — 4th tab "Roster Impact".
- **Generate** `data/projections.parquet` + commit `data/seed/projections.parquet`.

Tests run against the repo's local `data/`. Run with `uv run pytest`.

---

### Task 1: Projections fetch/parse/load (`ingestion/projections.py`)

**Files:**
- Modify: `config.py`
- Create: `ingestion/projections.py`
- Test: `tests/test_projections.py`

- [ ] **Step 1: Add the parquet path to `config.py`**

In `config.py`, after the line `NFL_DRAFT_PARQUET = DATA_DIR / "nfl_draft.parquet"`, add:

```python
PROJECTIONS_PARQUET = DATA_DIR / "projections.parquet"
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_projections.py`:

```python
# tests/test_projections.py
import pandas as pd

from ingestion.projections import _parse_projections, OUT_COLS

SAMPLE = [
    {"player_id": "4984",
     "player": {"first_name": "Josh", "last_name": "Allen", "position": "QB",
                "team": "BUF", "years_exp": 8},
     "stats": {"pts_ppr": 361.5, "pts_half_ppr": 361.5, "pts_std": 361.5}},
    {"player_id": "13287",
     "player": {"first_name": "Jeremiyah", "last_name": "Love", "position": "RB",
                "team": "FA", "years_exp": 0},
     "stats": {"pts_ppr": 239.0, "pts_half_ppr": 220.0, "pts_std": 200.0}},
    {"player_id": "999",
     "player": {"first_name": "Some", "last_name": "Kicker", "position": "K",
                "team": "NE", "years_exp": 3},
     "stats": {"pts_ppr": 150.0}},                       # non-skill -> dropped
    {"player_id": "888",
     "player": {"first_name": "No", "last_name": "Proj", "position": "WR",
                "team": "NE", "years_exp": 2},
     "stats": {"pts_ppr": None}},                        # null pts -> dropped
]


def test_parse_keeps_only_skill_with_pts():
    df = _parse_projections(SAMPLE)
    assert list(df.columns) == OUT_COLS
    assert len(df) == 2                                  # Allen + Love only
    assert set(df["position"]) <= {"QB", "RB", "WR", "TE"}


def test_parse_player_id_is_string_and_name_joined():
    df = _parse_projections(SAMPLE)
    row = df[df["player_id"] == "4984"].iloc[0]
    assert isinstance(row["player_id"], str)
    assert row["name"] == "Josh Allen"


def test_parse_sorted_by_pts_ppr_desc():
    df = _parse_projections(SAMPLE)
    assert df.iloc[0]["name"] == "Josh Allen"            # 361.5 before 239.0
    assert list(df["pts_ppr"]) == sorted(df["pts_ppr"], reverse=True)


def test_parse_empty_input():
    df = _parse_projections([])
    assert list(df.columns) == OUT_COLS
    assert df.empty
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_projections.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.projections'`

- [ ] **Step 4: Write the implementation**

Create `ingestion/projections.py`:

```python
# ingestion/projections.py
"""Sleeper season-long projections, keyed by Sleeper player_id so the join with
rosters/draft picks is lossless. See the Phase B design doc."""
import pandas as pd
import requests

from config import CURRENT_SEASON, PROJECTIONS_PARQUET

PROJECTIONS_URL = "https://api.sleeper.com/projections/nfl/{season}?season_type=regular"
SKILL = ["QB", "RB", "WR", "TE"]
OUT_COLS = ["player_id", "name", "position", "team",
            "pts_ppr", "pts_half_ppr", "pts_std", "years_exp"]


def _parse_projections(raw: list) -> pd.DataFrame:
    """Sleeper season rows -> tidy skill-player frame. Keeps QB/RB/WR/TE with a
    non-null pts_ppr; player_id is the Sleeper id (str). Sorted by pts_ppr desc."""
    rows = []
    for it in raw or []:
        pl = it.get("player") or {}
        stats = it.get("stats") or {}
        pos = pl.get("position")
        if pos not in SKILL or stats.get("pts_ppr") is None:
            continue
        rows.append({
            "player_id": str(it.get("player_id")),
            "name": f"{pl.get('first_name', '')} {pl.get('last_name', '')}".strip(),
            "position": pos,
            "team": pl.get("team"),
            "pts_ppr": stats.get("pts_ppr"),
            "pts_half_ppr": stats.get("pts_half_ppr"),
            "pts_std": stats.get("pts_std"),
            "years_exp": pl.get("years_exp"),
        })
    df = pd.DataFrame(rows, columns=OUT_COLS)
    if df.empty:
        return df
    return df.sort_values("pts_ppr", ascending=False).reset_index(drop=True)


def fetch_projections(season: int = CURRENT_SEASON) -> pd.DataFrame:
    resp = requests.get(PROJECTIONS_URL.format(season=season), timeout=60)
    resp.raise_for_status()
    return _parse_projections(resp.json())


def load_projections() -> pd.DataFrame:
    if not PROJECTIONS_PARQUET.exists():
        return pd.DataFrame(columns=OUT_COLS)
    return pd.read_parquet(PROJECTIONS_PARQUET)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_projections.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add config.py ingestion/projections.py tests/test_projections.py
git commit -m "feat(projections): fetch/parse Sleeper 2026 season projections"
```

---

### Task 2: Lineup math (`ingestion/roster_impact.py`)

**Files:**
- Modify: `config.py`
- Create: `ingestion/roster_impact.py`
- Test: `tests/test_roster_impact.py`

- [ ] **Step 1: Add starter counts to `config.py`**

In `config.py`, after the `POSITIONS = ["QB", "RB", "WR", "TE"]` line, add:

```python
# Starting-lineup counts for "points above starters" (user-defined: SF approximated
# by a 2nd QB). Used by the Roster Impact view.
STARTER_COUNTS = {"QB": 2, "RB": 3, "WR": 4, "TE": 2}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_roster_impact.py`:

```python
# tests/test_roster_impact.py
import pandas as pd
import pytest

from ingestion.roster_impact import starter_points, points_above_starters

COUNTS = {"QB": 2, "RB": 3, "WR": 4, "TE": 2}


def _df(rows):
    # rows: list of (position, pts)
    return pd.DataFrame(rows, columns=["position", "pts"])


def test_starter_points_top_n_per_position():
    # 3 QBs, take top 2 -> 300 + 250
    df = _df([("QB", 300), ("QB", 250), ("QB", 200)])
    assert starter_points(df, COUNTS, "pts") == pytest.approx(550)


def test_starter_points_multi_position_sum():
    df = _df([("QB", 300), ("QB", 250), ("RB", 100), ("RB", 90), ("RB", 80),
              ("RB", 70), ("WR", 50), ("TE", 40)])
    # QB top2: 550 ; RB top3: 270 ; WR top4: 50 ; TE top2: 40 -> 910
    assert starter_points(df, COUNTS, "pts") == pytest.approx(910)


def test_starter_points_fewer_than_n_sums_available():
    df = _df([("QB", 300)])                 # only 1 QB though counts asks 2
    assert starter_points(df, COUNTS, "pts") == pytest.approx(300)


def test_above_starters_upgrade_is_marginal():
    base = _df([("QB", 300), ("QB", 250)])  # both QB slots filled
    add = _df([("QB", 280)])                # cracks lineup, benches the 250
    # new top2 = 300 + 280 = 580 ; old = 550 -> +30
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(30)


def test_above_starters_below_cutoff_is_zero():
    base = _df([("QB", 300), ("QB", 250)])
    add = _df([("QB", 150)])                # worse than worst starter -> no change
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(0)


def test_above_starters_two_rookies_displace_two_starters():
    base = _df([("RB", 100), ("RB", 90), ("RB", 80)])   # top3 = 270
    add = _df([("RB", 110), ("RB", 95)])                # new top3 = 110+100+95=305
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(35)


def test_above_starters_empty_added_is_zero():
    base = _df([("QB", 300), ("QB", 250)])
    add = pd.DataFrame(columns=["position", "pts"])
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(0)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_roster_impact.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.roster_impact'`

- [ ] **Step 4: Write the implementation**

Create `ingestion/roster_impact.py`:

```python
# ingestion/roster_impact.py
"""Pure starting-lineup math for the Roster Impact view. No Streamlit.

starter_points sums each position's top-N projections; points_above_starters is the
marginal lineup upgrade from adding players (drafted rookies) to a baseline roster."""
import pandas as pd

from config import STARTER_COUNTS


def starter_points(players: pd.DataFrame, counts: dict | None = None,
                   score_col: str = "pts") -> float:
    """Sum of each position's top-N projections (the starting-lineup baseline).

    players: DataFrame with 'position' and score_col columns. counts defaults to
    STARTER_COUNTS. Missing positions / fewer than N players contribute what exists."""
    counts = counts or STARTER_COUNTS
    total = 0.0
    for pos, n in counts.items():
        pts = players.loc[players["position"] == pos, score_col]
        total += float(pts.sort_values(ascending=False).head(n).sum())
    return total


def points_above_starters(baseline: pd.DataFrame, added: pd.DataFrame,
                          counts: dict | None = None, score_col: str = "pts") -> float:
    """Marginal lineup upgrade: starter_points(baseline+added) − starter_points(baseline).

    A player who can't beat the worst starter at its position contributes 0; several
    additions at one position displace several starters correctly."""
    counts = counts or STARTER_COUNTS
    combined = pd.concat([baseline, added], ignore_index=True)
    return (starter_points(combined, counts, score_col)
            - starter_points(baseline, counts, score_col))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_roster_impact.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add config.py ingestion/roster_impact.py tests/test_roster_impact.py
git commit -m "feat(roster-impact): pure starter-points + above-starters math"
```

---

### Task 3: Seed + refresh plumbing + generate projections data

**Files:**
- Modify: `ingestion/seed.py`
- Modify: `components/sidebar.py`
- Modify: `tools/refresh_rankings.py`
- Test: `tests/test_seed.py`
- Generate: `data/projections.parquet`, `data/seed/projections.parquet`

- [ ] **Step 1: Add projections to the seed list (with a test)**

Append to `tests/test_seed.py`:

```python
def test_projections_in_seed_files():
    from ingestion.seed import SEED_FILES
    assert "projections.parquet" in SEED_FILES
```

Run: `uv run pytest tests/test_seed.py::test_projections_in_seed_files -v`
Expected: FAIL.

Then in `ingestion/seed.py`, change `SEED_FILES` to include the projections parquet:

```python
SEED_FILES = [
    "fantasycalc.parquet", "ktc.parquet", "merged.parquet", "nfl_draft.parquet",
    "projections.parquet",
    "lateround_rankings.csv", "adp_rankings.csv",
]
```

Run: `uv run pytest tests/test_seed.py -v`
Expected: PASS.

- [ ] **Step 2: Fetch projections in the sidebar refresh**

In `components/sidebar.py`, inside `_refresh_data()`, after the NFL-draft `try/except` block (the one ending with `st.write(f"NFL draft fetch failed — keeping existing ({e})")`) and BEFORE `st.write("Matching players...")`, add:

```python
        st.write("Fetching 2026 projections...")
        try:
            from ingestion.projections import fetch_projections
            from config import PROJECTIONS_PARQUET
            pr = fetch_projections()
            pr.to_parquet(PROJECTIONS_PARQUET, index=False)
            st.write(f"Projections: {len(pr)} skill players")
        except Exception as e:
            st.write(f"Projections fetch failed — keeping existing ({e})")
```

Also add a freshness line: in `render_sidebar`, after the line `_fresh(ADP_CSV, "ADP")`, add:

```python
    from config import PROJECTIONS_PARQUET
    _fresh(PROJECTIONS_PARQUET, "Projections")
```

- [ ] **Step 3: Fetch projections in the CLI refresh**

In `tools/refresh_rankings.py`, after the NFL-draft `try/except` block (ending `print(f"  NFL draft fetch failed ({e}) — keeping existing file")`) and BEFORE `print("Matching players...")`, add:

```python
    print("Fetching 2026 projections...")
    from ingestion.projections import fetch_projections
    from config import PROJECTIONS_PARQUET
    try:
        pr = fetch_projections()
        pr.to_parquet(PROJECTIONS_PARQUET, index=False)
        print(f"  Projections: {len(pr)} skill players")
    except Exception as e:
        print(f"  Projections fetch failed ({e}) — keeping existing file")
```

- [ ] **Step 4: Generate the data file and seed it**

Run the CLI helper to fetch live projections and write the parquet, then copy to the seed dir:

```bash
uv run python - <<'PY'
from ingestion.projections import fetch_projections
from config import PROJECTIONS_PARQUET, SEED_DIR
import shutil
df = fetch_projections()
df.to_parquet(PROJECTIONS_PARQUET, index=False)
SEED_DIR.mkdir(parents=True, exist_ok=True)
shutil.copy(PROJECTIONS_PARQUET, SEED_DIR / "projections.parquet")
print("rows:", len(df), "| rookies:", int((df["years_exp"] == 0).sum()))
print("sample:", df.iloc[0].to_dict())
PY
```

Expected: `rows:` ~800+ and `rookies:` ~100, sample is a top QB/RB.

Verify `load_projections()` returns the rows:

```bash
uv run python -c "from ingestion.projections import load_projections; print(len(load_projections()))"
```

Expected: same row count (>0).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit (including the committed seed file)**

```bash
git add ingestion/seed.py components/sidebar.py tools/refresh_rankings.py \
        tests/test_seed.py data/seed/projections.parquet
git commit -m "feat(projections): seed + sidebar/CLI refresh; ship 2026 projections seed"
```

Note: `data/projections.parquet` itself is gitignored (only `data/seed/` is committed) — that's intended; `ensure_data_from_seed()` copies the seed into `data/` on a fresh clone.

---

### Task 4: Roster Impact view (`views/roster_impact.py`)

**Files:**
- Create: `views/roster_impact.py`

No new unit test (Streamlit-bound; smoke-tested in Task 5). Pure math is already covered.

- [ ] **Step 1: Create the view module**

Create `views/roster_impact.py`:

```python
# views/roster_impact.py
"""Roster Impact tab: 2026 projected points each manager's rookie haul adds to their
roster — total, and the marginal upgrade to their starting lineup. See Phase B design."""
import pandas as pd
import streamlit as st

from config import STARTER_COUNTS
from ingestion.match_util import normalize_name
from ingestion.roster_impact import points_above_starters

SCORE_OPTIONS = {"PPR": "pts_ppr", "Half PPR": "pts_half_ppr", "Standard": "pts_std"}


def _collect_drafted(rookies, draft, league_id):
    """{manager: [sleeper_player_id, ...]} from the live draft, mock as fallback."""
    if draft and draft.get("draft_id"):
        from ingestion.sleeper import get_draft_picks, build_roster_to_manager
        try:
            picks = get_draft_picks(draft["draft_id"])
        except Exception:
            picks = []
        if picks:
            roster_to_mgr = build_roster_to_manager(league_id) if league_id else {}
            out = {}
            for pk in picks:
                pid = pk.get("player_id")
                if not pid:
                    continue
                mgr = roster_to_mgr.get(pk.get("roster_id"), f"Team {pk.get('roster_id')}")
                out.setdefault(mgr, []).append(str(pid))
            if out:
                return out
    # mock fallback: map pick player names -> sleeper_id via the rookies frame
    picks = st.session_state.get("draft_picks") or []
    if not picks:
        return {}
    name_to_id = {}
    for _, r in rookies.iterrows():
        if pd.notna(r.get("sleeper_id")):
            name_to_id[normalize_name(str(r["name"]))] = str(r["sleeper_id"])
    out = {}
    for p in picks:
        pid = name_to_id.get(normalize_name(str(p.get("player", ""))))
        if not pid:
            continue
        out.setdefault(p.get("owner", "?"), []).append(pid)
    return out


def render_roster_impact(rookies, draft, league_id):
    st.subheader("Roster Impact — 2026 Projections")

    from ingestion.projections import load_projections
    proj = load_projections()
    if proj.empty:
        st.info("No 2026 projections loaded. Click **Refresh Data** in the sidebar.")
        return
    proj = proj.copy()
    proj["player_id"] = proj["player_id"].astype(str)
    proj_idx = proj.set_index("player_id")

    score_label = st.radio("Scoring", list(SCORE_OPTIONS), horizontal=True, key="ri_score")
    score_col = SCORE_OPTIONS[score_label]

    drafted = _collect_drafted(rookies, draft, league_id)
    if not drafted:
        st.info("No draft picks yet — start your live draft or run a mock "
                "in the Mock Draft Simulator.")
        return

    # baseline rosters (existing players), keyed by manager
    roster_ids = {}
    if league_id:
        from ingestion.sleeper import get_rosters, build_roster_to_manager
        roster_to_mgr = build_roster_to_manager(league_id)
        for r in get_rosters(league_id):
            mgr = roster_to_mgr.get(r["roster_id"], f"Team {r['roster_id']}")
            roster_ids[mgr] = set(str(p) for p in (r.get("players") or []))

    def _frame(ids):
        ids = [i for i in ids if i in proj_idx.index]
        if not ids:
            return pd.DataFrame({"position": [], score_col: [], "name": []})
        return proj_idx.loc[ids, ["position", score_col, "name"]].reset_index()

    rows, total_roster, matched_roster = [], 0, 0
    for mgr, added_ids in drafted.items():
        added_ids = [str(i) for i in added_ids]
        base_ids = roster_ids.get(mgr, set()) - set(added_ids)   # never double-count
        total_roster += len(base_ids)
        matched_roster += sum(1 for i in base_ids if i in proj_idx.index)
        base_df = _frame(list(base_ids))
        add_df = _frame(added_ids)
        total_added = float(add_df[score_col].sum()) if not add_df.empty else 0.0
        above = points_above_starters(base_df, add_df, STARTER_COUNTS, score_col)
        rows.append({"manager": mgr, "total_added": round(total_added, 1),
                     "above_starters": round(above, 1)})
    summary = pd.DataFrame(rows).set_index("manager").sort_values(
        "above_starters", ascending=False)

    if total_roster:
        st.caption(f"Projection coverage: {matched_roster}/{total_roster} rostered "
                   f"players matched · scoring {score_label}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Total projected pts added**")
        st.bar_chart(summary["total_added"])
    with c2:
        st.markdown("**Pts added above starters**")
        st.bar_chart(summary["above_starters"])

    st.markdown("---")
    for mgr in summary.index:
        add_df = _frame([str(i) for i in drafted[mgr]])
        if not add_df.empty:
            add_df = add_df.sort_values(score_col, ascending=False)
        head = (f"{mgr} — +{summary.loc[mgr, 'above_starters']:.0f} above starters · "
                f"{summary.loc[mgr, 'total_added']:.0f} total")
        with st.expander(head):
            if add_df.empty:
                st.caption("No projected rookies drafted.")
            else:
                for _, p in add_df.iterrows():
                    st.markdown(f"- **{p['name']}** {p['position']} · "
                                f"{p[score_col]:.0f} pts")
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run python -c "import views.roster_impact; print('ok')"`
Expected: `ok`

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add views/roster_impact.py
git commit -m "feat(roster-impact): view — projected points added + above starters"
```

---

### Task 5: Wire the "Roster Impact" tab + smoke

**Files:**
- Modify: `views/draft_wizard.py` (`render()` tabs block, ~lines 585–597)

- [ ] **Step 1: Add the fourth tab**

In `views/draft_wizard.py` `render()`, find the current three-tab block:

```python
    tab_board, tab_mock, tab_recap = st.tabs(
        ["Draft Board", "Mock Draft Simulator", "Draft Recap"])

    with tab_board:
        _render_draft_board(rookies, available, rank_col, source_label, draft)

    with tab_mock:
        _render_mock_draft(rookies, draft_order, rank_col, num_teams,
                           num_rounds, user_slot, rules)

    with tab_recap:
        from views.draft_value import render_draft_value_recap
        render_draft_value_recap(rookies, draft, st.session_state.get("league_id", ""))
```

Replace it with (adds `tab_impact`):

```python
    tab_board, tab_mock, tab_recap, tab_impact = st.tabs(
        ["Draft Board", "Mock Draft Simulator", "Draft Recap", "Roster Impact"])

    with tab_board:
        _render_draft_board(rookies, available, rank_col, source_label, draft)

    with tab_mock:
        _render_mock_draft(rookies, draft_order, rank_col, num_teams,
                           num_rounds, user_slot, rules)

    with tab_recap:
        from views.draft_value import render_draft_value_recap
        render_draft_value_recap(rookies, draft, st.session_state.get("league_id", ""))

    with tab_impact:
        from views.roster_impact import render_roster_impact
        render_roster_impact(rookies, draft, st.session_state.get("league_id", ""))
```

If the block doesn't match exactly, STOP and report NEEDS_CONTEXT.

- [ ] **Step 2: Write the AppTest smoke script**

Write `/tmp/verify_impact.py` (one-time verification, not committed; connected path mirrors the repo's existing AppTest verifications and needs network for Sleeper):

```python
"""Verify the Roster Impact tab renders without exception (mock-fallback path)."""
import sys
sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard")
from streamlit.testing.v1 import AppTest
from views.draft_wizard import _get_rookies


def base():
    at = AppTest.from_file("/Users/nick/projects/dynasty-dashboard/streamlit_app.py",
                           default_timeout=180)
    at.session_state["sleeper_username"] = "brochillington"
    at.session_state["sleeper_display_name"] = "brochillington"
    at.session_state["user_id"] = "468958591886290944"
    at.session_state["league_id"] = "1312130398133694464"
    at.session_state["league_name"] = "Make it (dy)Nasty"
    at.session_state["ownership_map"] = {}
    at.session_state["selected_tool"] = "Draft Wizard"
    return at


rookies = _get_rookies("blended_rank")
names = rookies["name"].head(6).tolist()
mock = [
    {"player": names[i], "owner": ("You" if i % 2 == 0 else "Team 2"),
     "player_pos": rookies.iloc[i]["position"], "player_rank": i + 1,
     "pick": i + 1, "round": 1, "round_pick": i + 1, "is_user": i % 2 == 0}
    for i in range(6)
]

at = base()
at.session_state["draft_picks"] = mock
at.run()
assert not at.exception, [repr(e.value)[:400] for e in at.exception]
md = " ".join(m.value for m in at.markdown)
subs = " ".join(s.value for s in at.subheader)
print("Tab title present:", "Roster Impact" in subs)
print("Total chart label:", "Total projected pts added" in md)
print("Above-starters chart label:", "Pts added above starters" in md)
ok = ("Roster Impact" in subs
      and "Total projected pts added" in md
      and "Pts added above starters" in md)
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 3: Run the smoke + full suite**

Run: `uv run python /tmp/verify_impact.py`
Expected: `Tab title present: True`, `Total chart label: True`, `Above-starters chart label: True`, `PASS`.

If it FAILS with an exception, read it and fix the genuine cause in `views/roster_impact.py` (e.g. a KeyError, an empty-frame chart, a format on None) and re-run. If it fails only because the live Sleeper API is unreachable (so rosters/projections can't load), report DONE_WITH_CONCERNS describing exactly what failed.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add views/draft_wizard.py
git commit -m "feat(draft-wizard): wire Roster Impact tab"
```

---

## Final review

After all tasks, dispatch a final code review of the whole branch (`ingestion/projections.py`, `ingestion/roster_impact.py`, `views/roster_impact.py`, config/seed/sidebar/CLI edits, the tab wiring, the committed seed parquet, tests), then use **superpowers:finishing-a-development-branch** to merge `roster-projection-impact` into `main` and push (the user deploys Streamlit Cloud from `main`).
