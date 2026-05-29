# Draft App Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ADP + NFL draft-capital ranking sources, an equal-weight 5-source rookie blend, best-available decision cards (live + mock), sortable mobile board with a Biggest-Disagreements view, and a seed-snapshot Streamlit Cloud deploy.

**Architecture:** New pure-logic + ingestion modules (`ingestion/blend.py`, `ingestion/match_util.py`, `ingestion/nfl_draft.py`, `ingestion/adp.py`) feed an enhanced `views/draft_wizard.py::_get_rookies()`. Shared UI render helpers live in `views/draft_board.py` and are reused by the first page (live picks) and the mock simulator (simulated picks). A seed bootstrap lets the gitignored `data/` populate from committed `data/seed/` on Streamlit Cloud.

**Tech Stack:** Python 3.12, Streamlit, pandas/pyarrow, requests, nflverse parquet release, pytest, uv.

---

## File Structure

- Create `ingestion/blend.py` — pure blend + spread math (TDD).
- Create `ingestion/match_util.py` — shared name normalize + fuzzy source-attach (TDD).
- Create `ingestion/nfl_draft.py` — fetch/compute/merge NFL draft capital (TDD on rank logic).
- Create `ingestion/adp.py` — load/merge ADP CSV.
- Create `ingestion/seed.py` — copy `data/seed/*` → `data/` if missing.
- Create `views/draft_board.py` — shared cards/board/disagreements render helpers.
- Create `tests/test_blend.py`, `tests/test_match_util.py`, `tests/test_nfl_draft.py`, `tests/test_adp.py`, `tests/test_get_rookies.py`, `tests/test_seed.py`.
- Modify `config.py` — paths + blend defaults.
- Modify `views/draft_wizard.py` — `_get_rookies`, `RANK_SOURCES`, board/mock wiring, mobile controls.
- Modify `ingestion/sleeper.py` — shorten `get_draft_picks` TTL.
- Modify `components/sidebar.py` — per-source freshness + refresh new sources.
- Modify `tools/refresh_rankings.py` — fetch NFL draft (+ note ADP/LR are manual).
- Modify `streamlit_app.py` — call seed bootstrap.
- Modify `.gitignore` — un-ignore `data/seed/`.
- Create `.streamlit/config.toml`, `requirements.txt`, `data/seed/*`.

---

## Task 1: Blend + spread pure logic

**Files:**
- Create: `ingestion/blend.py`
- Test: `tests/test_blend.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_blend.py
from ingestion.blend import blend_rank, rank_spread

def test_blend_equal_weights_all_present():
    sr = {"lr": 4, "fc": 14, "ktc": 12, "draft": 7, "adp": 5}
    w = {k: 0.2 for k in sr}
    assert blend_rank(sr, w) == (4 + 14 + 12 + 7 + 5) / 5  # 8.4

def test_blend_renormalizes_missing_source():
    sr = {"lr": 4, "fc": 14, "ktc": 12, "draft": 7, "adp": None}
    w = {k: 0.2 for k in sr}
    assert blend_rank(sr, w) == (4 + 14 + 12 + 7) / 4  # 9.25

def test_blend_none_when_no_sources():
    assert blend_rank({"lr": None, "fc": None}, {"lr": 0.5, "fc": 0.5}) is None

def test_blend_respects_unequal_weights():
    sr = {"lr": 10, "fc": 20}
    assert blend_rank(sr, {"lr": 0.75, "fc": 0.25}) == 10 * 0.75 + 20 * 0.25  # 12.5

def test_rank_spread_basic():
    sr = {"lr": 3, "fc": 14, "ktc": 12, "draft": 7, "adp": 5}
    spread, high, low = rank_spread(sr)
    assert spread == 14 - 3
    assert high == "lr"   # most bullish = lowest rank number
    assert low == "fc"    # most bearish = highest rank number

def test_rank_spread_needs_two_sources():
    assert rank_spread({"lr": 3, "fc": None}) == (None, None, None)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_blend.py -v`
Expected: FAIL (ModuleNotFoundError: ingestion.blend)

- [ ] **Step 3: Implement**

```python
# ingestion/blend.py
"""Pure equal/weighted blend + disagreement-spread math over per-source ranks."""


def blend_rank(source_ranks: dict, weights: dict):
    """Weighted mean of present source ranks, renormalized over present sources.
    source_ranks: {key: rank or None}. weights: {key: weight}. None if none present."""
    num = 0.0
    den = 0.0
    for key, rank in source_ranks.items():
        if rank is None:
            continue
        w = weights.get(key, 0.0)
        if w <= 0:
            continue
        num += rank * w
        den += w
    return num / den if den > 0 else None


def rank_spread(source_ranks: dict):
    """(spread, high_source, low_source) over present ranks; needs >=2 present.
    high_source = most bullish (lowest rank number), low_source = most bearish."""
    present = {k: r for k, r in source_ranks.items() if r is not None}
    if len(present) < 2:
        return None, None, None
    high = min(present, key=present.get)
    low = max(present, key=present.get)
    return present[low] - present[high], high, low
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_blend.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/blend.py tests/test_blend.py
git commit -m "feat(blend): equal-weight rookie blend + disagreement spread"
```

---

## Task 2: Shared name-match helper

**Files:**
- Create: `ingestion/match_util.py`
- Test: `tests/test_match_util.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_match_util.py
import pandas as pd
from ingestion.match_util import normalize_name, attach_source_ranks

def test_normalize_strips_suffix_and_punct():
    assert normalize_name("Omar Cooper Jr.") == "omar cooper"
    assert normalize_name("Ja'Marr Chase") == "jamarr chase"

def test_attach_exact_and_fuzzy():
    rookies = pd.DataFrame([
        {"name": "Omar Cooper Jr.", "position": "WR"},
        {"name": "Jeremiyah Love", "position": "RB"},
        {"name": "Nobody Here", "position": "TE"},
    ])
    src = pd.DataFrame([
        {"name": "Omar Cooper", "position": "WR", "adp_rank": 9},   # exact after normalize
        {"name": "Jeremiah Love", "position": "RB", "adp_rank": 1}, # fuzzy (one letter)
    ])
    out = attach_source_ranks(rookies, src, ["adp_rank"])
    assert out.loc[0, "adp_rank"] == 9
    assert out.loc[1, "adp_rank"] == 1
    assert pd.isna(out.loc[2, "adp_rank"])

def test_attach_empty_source_adds_null_cols():
    rookies = pd.DataFrame([{"name": "X", "position": "WR"}])
    out = attach_source_ranks(rookies, pd.DataFrame(), ["adp_rank"])
    assert "adp_rank" in out.columns and pd.isna(out.loc[0, "adp_rank"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_match_util.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# ingestion/match_util.py
"""Shared name normalization + fuzzy source-rank attachment (name + position)."""
import re
from difflib import SequenceMatcher

import pandas as pd

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_NON_ALPHA_RE = re.compile(r"[^a-z\s]")


def normalize_name(name) -> str:
    n = str(name).lower().strip()
    n = _NON_ALPHA_RE.sub("", n)
    n = _SUFFIX_RE.sub("", n)
    return " ".join(n.split())


def attach_source_ranks(rookies: pd.DataFrame, src: pd.DataFrame,
                        cols: list[str], threshold: float = 0.80) -> pd.DataFrame:
    """Left-attach src[cols] onto rookies by normalized name+position (exact then
    fuzzy). Each src row used at most once. Adds `cols` (None where unmatched)."""
    rookies = rookies.copy()
    for c in cols:
        rookies[c] = None
    if src is None or src.empty:
        return rookies

    rookies["_norm"] = rookies["name"].apply(normalize_name)
    src = src.copy()
    src["_norm"] = src["name"].apply(normalize_name)
    used: set = set()

    # Pass 1: exact normalized name + position
    for r_idx, r in rookies.iterrows():
        m = src[(src["_norm"] == r["_norm"]) & (src["position"] == r["position"])
                & (~src.index.isin(used))]
        if len(m) >= 1:
            s_idx = m.index[0]
            used.add(s_idx)
            for c in cols:
                rookies.at[r_idx, c] = src.at[s_idx, c]

    # Pass 2: fuzzy for still-unmatched rookies (same position)
    unmatched = rookies[rookies[cols[0]].isna()]
    for r_idx, r in unmatched.iterrows():
        cands = src[(~src.index.isin(used)) & (src["position"] == r["position"])]
        best, best_idx = 0.0, None
        for s_idx, s in cands.iterrows():
            score = SequenceMatcher(None, r["_norm"], s["_norm"]).ratio()
            if score > best:
                best, best_idx = score, s_idx
        if best >= threshold and best_idx is not None:
            used.add(best_idx)
            for c in cols:
                rookies.at[r_idx, c] = src.at[best_idx, c]

    return rookies.drop(columns=["_norm"], errors="ignore")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_match_util.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/match_util.py tests/test_match_util.py
git commit -m "feat(match): shared normalized+fuzzy source-rank attach helper"
```

---

## Task 3: NFL draft capital source

**Files:**
- Create: `ingestion/nfl_draft.py`
- Modify: `config.py`
- Test: `tests/test_nfl_draft.py`

- [ ] **Step 1: Add config paths**

In `config.py`, after the existing data-path block (`MERGED_PARQUET = ...`), add:

```python
NFL_DRAFT_PARQUET = DATA_DIR / "nfl_draft.parquet"
ADP_CSV = DATA_DIR / "adp_rankings.csv"
SEED_DIR = DATA_DIR / "seed"

# Equal-weight rookie blend across the 5 sources
BLEND_WEIGHTS_DEFAULT = {"lr": 0.20, "fc": 0.20, "ktc": 0.20, "draft": 0.20, "adp": 0.20}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_nfl_draft.py
import pandas as pd
from ingestion.nfl_draft import _compute_draft_ranks

def _raw():
    # mimic nflverse columns; mix of skill + non-skill + wrong season
    return pd.DataFrame([
        {"season": 2026, "pick": 1, "team": "LVR", "pfr_player_name": "Fernando Mendoza", "position": "QB", "college": "Indiana"},
        {"season": 2026, "pick": 2, "team": "X", "pfr_player_name": "Some Tackle", "position": "T", "college": "Y"},
        {"season": 2026, "pick": 3, "team": "ARI", "pfr_player_name": "Jeremiyah Love", "position": "RB", "college": "ND"},
        {"season": 2026, "pick": 4, "team": "TEN", "pfr_player_name": "Carnell Tate", "position": "WR", "college": "OSU"},
        {"season": 2026, "pick": 13, "team": "LAR", "pfr_player_name": "Ty Simpson", "position": "QB", "college": "Bama"},
        {"season": 2025, "pick": 1, "team": "Z", "pfr_player_name": "Old Guy", "position": "WR", "college": "Z"},
    ])

def test_skill_filter_and_overall_skill_rank():
    out = _compute_draft_ranks(_raw(), 2026)
    assert list(out["name"]) == ["Fernando Mendoza", "Jeremiyah Love", "Carnell Tate", "Ty Simpson"]
    assert list(out["draft_skill_rank"]) == [1, 2, 3, 4]  # dense by pick, skill only
    assert "Some Tackle" not in set(out["name"])  # non-skill dropped
    assert "Old Guy" not in set(out["name"])      # wrong season dropped

def test_positional_rank_by_pick():
    out = _compute_draft_ranks(_raw(), 2026)
    qbs = out[out["position"] == "QB"].sort_values("draft_overall_pick")
    assert list(qbs["draft_pos_rank"]) == [1, 2]  # Mendoza QB1, Simpson QB2

def test_empty_when_season_absent():
    out = _compute_draft_ranks(_raw(), 2099)
    assert out.empty
    assert set(["name", "draft_skill_rank", "draft_pos_rank"]).issubset(out.columns)
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_nfl_draft.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 4: Implement**

```python
# ingestion/nfl_draft.py
"""NFL draft capital as a ranking source (nflverse draft picks, skill positions)."""
import io

import pandas as pd
import requests

from config import CURRENT_SEASON, NFL_DRAFT_PARQUET
from ingestion.match_util import attach_source_ranks

NFLVERSE_DRAFT_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "draft_picks/draft_picks.parquet"
)
SKILL = ["QB", "RB", "WR", "TE"]
OUT_COLS = ["name", "position", "team", "college",
            "draft_overall_pick", "draft_skill_rank", "draft_pos_rank"]


def _compute_draft_ranks(raw: pd.DataFrame, season: int) -> pd.DataFrame:
    df = raw[(raw["season"] == season) & (raw["position"].isin(SKILL))].copy()
    if df.empty:
        return pd.DataFrame(columns=OUT_COLS)
    df = df.sort_values("pick").rename(
        columns={"pfr_player_name": "name", "pick": "draft_overall_pick"}
    )
    df["draft_skill_rank"] = range(1, len(df) + 1)
    df["draft_pos_rank"] = (
        df.groupby("position")["draft_overall_pick"].rank(method="first").astype(int)
    )
    for c in OUT_COLS:
        if c not in df.columns:
            df[c] = None
    return df[OUT_COLS].reset_index(drop=True)


def fetch_nfl_draft(season: int = CURRENT_SEASON) -> pd.DataFrame:
    resp = requests.get(NFLVERSE_DRAFT_URL, timeout=60)
    resp.raise_for_status()
    raw = pd.read_parquet(io.BytesIO(resp.content))
    return _compute_draft_ranks(raw, season)


def load_nfl_draft() -> pd.DataFrame:
    if not NFL_DRAFT_PARQUET.exists():
        return pd.DataFrame()
    return pd.read_parquet(NFL_DRAFT_PARQUET)


def merge_nfl_draft(rookies: pd.DataFrame, draft: pd.DataFrame) -> pd.DataFrame:
    return attach_source_ranks(
        rookies, draft,
        ["draft_skill_rank", "draft_pos_rank", "draft_overall_pick"],
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_nfl_draft.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Fetch + persist the real parquet, sanity check**

Run:
```bash
uv run python -c "from ingestion.nfl_draft import fetch_nfl_draft; from config import NFL_DRAFT_PARQUET; d=fetch_nfl_draft(); d.to_parquet(NFL_DRAFT_PARQUET, index=False); print(len(d), 'skill picks'); print(d.head(6).to_string())"
```
Expected: ~80 skill picks; Fernando Mendoza draft_skill_rank=1.

- [ ] **Step 7: Commit**

```bash
git add ingestion/nfl_draft.py tests/test_nfl_draft.py config.py
git commit -m "feat(nfl-draft): draft-capital source (overall skill + positional rank)"
```

---

## Task 4: ADP source

**Files:**
- Create: `ingestion/adp.py`
- Test: `tests/test_adp.py`
- (Data already present: `data/adp_rankings.csv`)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_adp.py
import pandas as pd
from ingestion.adp import merge_adp, _rename_adp

def test_rename_columns():
    raw = pd.DataFrame([{"rank": 1, "name": "A", "position": "RB", "pos_rank": 1, "adp": 1.1}])
    out = _rename_adp(raw)
    assert {"adp_rank", "adp_pos_rank", "adp_value"}.issubset(out.columns)
    assert out.loc[0, "adp_rank"] == 1 and out.loc[0, "adp_value"] == 1.1

def test_merge_adp_onto_rookies():
    rookies = pd.DataFrame([{"name": "Carnell Tate", "position": "WR"}])
    adp = pd.DataFrame([{"adp_rank": 2, "name": "Carnell Tate", "position": "WR", "adp_pos_rank": 1, "adp_value": 2.6}])
    out = merge_adp(rookies, adp)
    assert out.loc[0, "adp_rank"] == 2 and out.loc[0, "adp_value"] == 2.6
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_adp.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# ingestion/adp.py
"""Consensus rookie ADP source (manual CSV transcribed from the ADP board)."""
import pandas as pd

from config import ADP_CSV
from ingestion.match_util import attach_source_ranks


def _rename_adp(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={"rank": "adp_rank", "pos_rank": "adp_pos_rank", "adp": "adp_value"})


def load_adp() -> pd.DataFrame:
    if not ADP_CSV.exists():
        return pd.DataFrame()
    return _rename_adp(pd.read_csv(ADP_CSV))


def merge_adp(rookies: pd.DataFrame, adp: pd.DataFrame) -> pd.DataFrame:
    return attach_source_ranks(rookies, adp, ["adp_rank", "adp_pos_rank", "adp_value"])
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_adp.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/adp.py tests/test_adp.py
git commit -m "feat(adp): consensus ADP source + merge"
```

---

## Task 5: Enhance `_get_rookies` (5-source blend + spread)

**Files:**
- Modify: `views/draft_wizard.py` (top constants + `_get_rookies`)
- Test: `tests/test_get_rookies.py`

- [ ] **Step 1: Replace `RANK_SOURCES` and add source maps**

In `views/draft_wizard.py`, replace the existing `RANK_SOURCES = {...}` block (lines ~9-14) with:

```python
RANK_SOURCES = {
    "Blended (avg)": "blended_rank",
    "ADP": "adp_rank",
    "NFL Draft": "draft_skill_rank",
    "LateRound": "lr_rank",
    "FantasyCalc": "fc_rookie_rank",
    "KeepTradeCut": "ktc_rookie_rank",
}

SOURCE_RANK_COLS = {
    "lr": "lr_rank", "fc": "fc_rookie_rank", "ktc": "ktc_rookie_rank",
    "draft": "draft_skill_rank", "adp": "adp_rank",
}
SOURCE_LABELS = {"lr": "LR", "fc": "FC", "ktc": "KTC", "draft": "Draft", "adp": "ADP"}
```

Add to the imports at the top of the file:

```python
from config import MERGED_PARQUET, POSITIONS, BLEND_WEIGHTS_DEFAULT
```
(replace the existing `from config import MERGED_PARQUET, POSITIONS` line).

- [ ] **Step 2: Replace the `_get_rookies` function body**

Replace the whole existing `_get_rookies(...)` function with:

```python
def _get_rookies(rank_col: str, blend_weights: dict | None = None) -> pd.DataFrame:
    from ingestion.lateround import load_lateround, merge_lateround
    from ingestion.nfl_draft import load_nfl_draft, merge_nfl_draft
    from ingestion.adp import load_adp, merge_adp
    from ingestion.blend import blend_rank, rank_spread

    if blend_weights is None:
        blend_weights = dict(BLEND_WEIGHTS_DEFAULT)

    df = pd.read_parquet(MERGED_PARQUET)
    rookies = df[df["is_rookie"] == True].copy()  # noqa: E712

    # LateRound (rank, not tier)
    lr = load_lateround()
    if not lr.empty:
        rookies = merge_lateround(rookies, lr)
    for c in ("lr_rank", "lr_pos_rank", "lr_tier"):
        if c not in rookies.columns:
            rookies[c] = None

    # NFL draft capital + ADP
    rookies = merge_nfl_draft(rookies, load_nfl_draft())
    rookies = merge_adp(rookies, load_adp())

    # Rookie-only FC/KTC ranks (comparable to LR/Draft/ADP ranks)
    for src, col in [("fc", "fc_rank"), ("ktc", "ktc_rank")]:
        rookie_col = f"{src}_rookie_rank"
        subset = rookies[rookies[col].notna()].sort_values(col)
        rookies[rookie_col] = None
        rookies.loc[subset.index, rookie_col] = range(1, len(subset) + 1)

    # Equal-weight blend + disagreement spread
    def _row(r):
        sr = {}
        for k, c in SOURCE_RANK_COLS.items():
            v = r.get(c)
            sr[k] = float(v) if pd.notna(v) else None
        b = blend_rank(sr, blend_weights)
        sp, hi, lo = rank_spread(sr)
        return pd.Series({
            "blended_rank": b,
            "rank_spread": sp,
            "source_high": SOURCE_LABELS.get(hi),
            "source_low": SOURCE_LABELS.get(lo),
        })

    rookies[["blended_rank", "rank_spread", "source_high", "source_low"]] = \
        rookies.apply(_row, axis=1)

    rookies = rookies[rookies[rank_col].notna()]
    rookies = rookies.sort_values(rank_col).reset_index(drop=True)
    return rookies
```

- [ ] **Step 3: Write an integration test**

```python
# tests/test_get_rookies.py
import pandas as pd
from views.draft_wizard import _get_rookies, RANK_SOURCES

def test_get_rookies_has_all_source_ranks_and_blend():
    df = _get_rookies("blended_rank")
    assert len(df) > 0
    for col in ["blended_rank", "rank_spread", "adp_rank", "draft_skill_rank",
                "fc_rookie_rank", "ktc_rookie_rank", "lr_rank"]:
        assert col in df.columns, col
    # top blended rookie should be a real, well-known 2026 name
    assert df.iloc[0]["blended_rank"] is not None
    # spread present for players with >=2 sources
    assert df["rank_spread"].notna().any()

def test_rank_sources_resolve_to_columns():
    df = _get_rookies("blended_rank")
    for label, col in RANK_SOURCES.items():
        assert col in df.columns, f"{label}->{col}"
```

- [ ] **Step 4: Run integration test**

Run: `uv run pytest tests/test_get_rookies.py -v`
Expected: PASS (requires `data/merged.parquet` + `data/nfl_draft.parquet` + `data/adp_rankings.csv` present from earlier tasks).

- [ ] **Step 5: Commit**

```bash
git add views/draft_wizard.py tests/test_get_rookies.py
git commit -m "feat(draft-wizard): 5-source equal-weight rookie blend + spread"
```

---

## Task 6: Shared render helpers (cards, board, disagreements)

**Files:**
- Create: `views/draft_board.py`

- [ ] **Step 1: Implement render helpers**

```python
# views/draft_board.py
"""Shared rookie render helpers reused by the live Draft Board and the mock."""
import pandas as pd
import streamlit as st

from config import POSITIONS

POS_COLORS = {"QB": "#e41a1c", "RB": "#377eb8", "WR": "#4daf4a", "TE": "#ff7f00"}

BOARD_COLS = ["name", "position", "team", "blended_rank", "adp_rank",
              "draft_skill_rank", "lr_rank", "fc_rookie_rank", "ktc_rookie_rank",
              "rank_spread", "age", "college"]

DISAGREE_COLS = ["name", "position", "blended_rank", "lr_rank", "fc_rookie_rank",
                 "ktc_rookie_rank", "draft_skill_rank", "adp_rank", "rank_spread",
                 "source_high", "source_low"]


def _fmt(v, spec="{:.0f}"):
    return spec.format(v) if pd.notna(v) else "—"


def _board_col_config():
    n = st.column_config.NumberColumn
    return {
        "name": st.column_config.TextColumn("Player", width="medium"),
        "position": st.column_config.TextColumn("Pos", width="small"),
        "team": st.column_config.TextColumn("Tm", width="small"),
        "blended_rank": n("Blend#", format="%.1f"),
        "adp_rank": n("ADP#", format="%d"),
        "draft_skill_rank": n("Draft#", format="%d"),
        "lr_rank": n("LR#", format="%d"),
        "fc_rookie_rank": n("FC#", format="%d"),
        "ktc_rookie_rank": n("KTC#", format="%d"),
        "rank_spread": n("Spread", format="%.0f"),
        "age": n("Age", format="%.1f"),
        "source_high": st.column_config.TextColumn("Bull"),
        "source_low": st.column_config.TextColumn("Bear"),
        "college": st.column_config.TextColumn("College"),
    }


def _player_card(p: pd.Series):
    color = POS_COLORS.get(p["position"], "#666")
    age = f"{p['age']:.1f}" if pd.notna(p.get("age")) else "—"
    draft = f"{_fmt(p.get('draft_skill_rank'))} (pk {_fmt(p.get('draft_overall_pick'))})"
    note = ""
    if pd.notna(p.get("source_high")) and pd.notna(p.get("source_low")):
        note = f"{p['source_high']} loves / {p['source_low']} fades"
    st.markdown(
        f"<div style='border:1px solid #444;border-left:5px solid {color};"
        f"border-radius:8px;padding:8px 10px;margin:3px 0;background:#1a1a2e'>"
        f"<div style='font-weight:bold'>{p['name']}</div>"
        f"<div style='font-size:0.72em;color:#aaa'>{p['position']} · {p.get('team','')} · "
        f"age {age} · {p.get('college','') or ''}</div>"
        f"<div style='font-size:0.8em;margin-top:4px'>Blend <b>{_fmt(p.get('blended_rank'),'{:.1f}')}</b>"
        f" · ADP {_fmt(p.get('adp_rank'))} · Draft {draft}</div>"
        f"<div style='font-size:0.74em;color:#bbb'>LR {_fmt(p.get('lr_rank'))} · "
        f"FC {_fmt(p.get('fc_rookie_rank'))} · KTC {_fmt(p.get('ktc_rookie_rank'))} · "
        f"spread {_fmt(p.get('rank_spread'))}</div>"
        f"<div style='font-size:0.68em;color:#888'>{note}</div>"
        f"</div>", unsafe_allow_html=True)


def render_best_available_cards(available: pd.DataFrame, rank_col: str, top_n: int = 2):
    st.markdown("#### Best Available by Position")
    for pos in POSITIONS:
        pool = available[available["position"] == pos].sort_values(rank_col).head(top_n)
        if pool.empty:
            continue
        st.caption(pos)
        cols = st.columns(len(pool))
        for col, (_, p) in zip(cols, pool.iterrows()):
            with col:
                _player_card(p)


def render_sortable_board(rookies: pd.DataFrame):
    cols = [c for c in BOARD_COLS if c in rookies.columns]
    st.dataframe(rookies[cols], use_container_width=True, hide_index=True,
                 column_config=_board_col_config())


def render_disagreements(rookies: pd.DataFrame, n: int = 15):
    st.markdown("#### Biggest Disagreements")
    st.caption("Sorted by spread across LR / FC / KTC / Draft / ADP — value or trap")
    d = rookies[rookies["rank_spread"].notna()].sort_values("rank_spread", ascending=False).head(n)
    cols = [c for c in DISAGREE_COLS if c in d.columns]
    st.dataframe(d[cols], use_container_width=True, hide_index=True,
                 column_config=_board_col_config())
```

- [ ] **Step 2: Smoke-import**

Run: `uv run python -c "import views.draft_board; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add views/draft_board.py
git commit -m "feat(draft-board): shared cards, sortable board, disagreements helpers"
```

---

## Task 7: Live availability helper (Sleeper picks)

**Files:**
- Modify: `ingestion/sleeper.py` (shorten `get_draft_picks` TTL)
- Modify: `views/draft_wizard.py` (add `_available_after_live_picks`)

- [ ] **Step 1: Shorten live-picks TTL**

In `ingestion/sleeper.py`, change the decorator on `get_draft_picks` from `@st.cache_data(ttl=300)` to:

```python
@st.cache_data(ttl=30)
def get_draft_picks(draft_id: str) -> list[dict]:
```

- [ ] **Step 2: Add availability helper in `views/draft_wizard.py`**

Add near the top of `views/draft_wizard.py` (after imports):

```python
def _available_after_live_picks(rookies: pd.DataFrame, draft_id: str) -> pd.DataFrame:
    """Remove rookies already taken in the live Sleeper draft (by sleeper_id then name)."""
    from ingestion.sleeper import get_draft_picks
    from ingestion.match_util import normalize_name
    try:
        picks = get_draft_picks(draft_id)
    except Exception:
        return rookies
    taken_ids, taken_names = set(), set()
    for pk in picks or []:
        if pk.get("player_id"):
            taken_ids.add(str(pk["player_id"]))
        md = pk.get("metadata") or {}
        nm = f"{md.get('first_name','')} {md.get('last_name','')}".strip()
        if nm:
            taken_names.add(normalize_name(nm))
    if "sleeper_id" in rookies.columns:
        mask_id = rookies["sleeper_id"].astype(str).isin(taken_ids)
    else:
        mask_id = pd.Series(False, index=rookies.index)
    mask_name = rookies["name"].apply(lambda n: normalize_name(n) in taken_names)
    return rookies[~(mask_id | mask_name)].copy()
```

- [ ] **Step 3: Smoke-import**

Run: `uv run python -c "import views.draft_wizard; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add ingestion/sleeper.py views/draft_wizard.py
git commit -m "feat(draft): live-pick availability helper + 30s picks TTL"
```

---

## Task 8: Wire Draft Board first page (cards + board + disagreements + mobile controls)

**Files:**
- Modify: `views/draft_wizard.py` (`render` + `_render_draft_board`)

- [ ] **Step 1: Move live controls to the main pane and add top_n**

In `render()`, the sidebar currently holds `source_label = st.sidebar.radio("Rank by", ...)`. Leave a fallback but add a **main-pane** control set. Replace the body of `render()` from the `# --- Tabs ---` section down to the two `with tab_*:` calls with:

```python
    rookies = _get_rookies(rank_col, blend_weights)

    # Live availability for the first-page cards/board
    available = rookies
    if draft and draft.get("draft_id"):
        available = _available_after_live_picks(rookies, draft["draft_id"])

    tab_board, tab_mock = st.tabs(["Draft Board", "Mock Draft Simulator"])

    with tab_board:
        _render_draft_board(rookies, available, rank_col, source_label, draft)

    with tab_mock:
        _render_mock_draft(rookies, draft_order, rank_col, num_teams,
                           num_rounds, user_slot, rules)
```

- [ ] **Step 2: Rewrite `_render_draft_board`**

Replace the existing `_render_draft_board(...)` function with:

```python
def _render_draft_board(rookies, available, rank_col, source_label, draft):
    from views.draft_board import (render_best_available_cards,
                                   render_sortable_board, render_disagreements)

    # Mobile-first controls in the main pane (not the sidebar drawer)
    c1, c2 = st.columns([2, 1])
    with c1:
        top_n = st.radio("Cards per position", [2, 3], horizontal=True,
                         index=0, key="dw_top_n")
    with c2:
        if draft and draft.get("draft_id"):
            if st.button("↻ Refresh picks", use_container_width=True):
                from ingestion.sleeper import get_draft_picks
                get_draft_picks.clear()
                st.rerun()

    n_taken = len(rookies) - len(available)
    if draft and draft.get("draft_id"):
        st.caption(f"Live: {n_taken} drafted · {len(available)} available · sorted by {source_label}")
    else:
        st.caption(f"No live draft connected — showing overall best available · sorted by {source_label}")

    render_best_available_cards(available, rank_col, top_n=top_n)

    st.markdown("---")
    pos_filter = st.radio("Position", ["All"] + POSITIONS, horizontal=True, key="dw_board_pos")
    board = available if pos_filter == "All" else available[available["position"] == pos_filter]
    render_sortable_board(board)

    st.markdown("---")
    render_disagreements(available)
```

- [ ] **Step 3: Headless verify (AppTest unconnected path + cards import)**

Run:
```bash
uv run python -c "
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('streamlit_app.py', default_timeout=30); at.run()
assert not at.exception, at.exception
from views.draft_wizard import _get_rookies
from views.draft_board import render_best_available_cards
r=_get_rookies('blended_rank'); print('rookies', len(r), 'cols ok', all(c in r.columns for c in ['blended_rank','adp_rank','draft_skill_rank','rank_spread']))
print('OK')
"
```
Expected: `OK`, rookies > 0, cols ok True.

- [ ] **Step 4: Commit**

```bash
git add views/draft_wizard.py
git commit -m "feat(draft-board): first-page cards + sortable board + disagreements + mobile controls"
```

---

## Task 9: Mock mirrors live (use shared cards in the mock; drop lr_tier)

**Files:**
- Modify: `views/draft_wizard.py` (`_render_mock_draft` user-turn block, `_render_draft_board_grid` columns, remove `lr_tier` usage)

- [ ] **Step 1: Use shared cards in the mock "your turn" view**

In `_render_mock_draft`, find the user-turn block beginning `st.markdown("**Best Available**")` through the `st.dataframe(pick_available...head(20)...)` call. Replace that dataframe rendering with the shared cards + sortable board so the mock mirrors the live page:

```python
    st.markdown("**Best Available**")
    from views.draft_board import render_best_available_cards, render_sortable_board
    pick_pos = st.radio("Filter", ["All"] + POSITIONS, horizontal=True, key="dw_pick_pos")
    if pick_pos != "All":
        pick_available = available[available["position"] == pick_pos]
    else:
        pick_available = available

    render_best_available_cards(pick_available, rank_col, top_n=3)
    render_sortable_board(pick_available.head(30))
```
(Keep the existing `selectbox` + `Draft` button block that follows unchanged.)

- [ ] **Step 2: Reduce the mock grid columns for phones**

In `_render_draft_board_grid`, change:
```python
        cols = st.columns(min(num_teams, 6))
```
to:
```python
        cols = st.columns(min(num_teams, 4))
```

- [ ] **Step 3: Remove `lr_tier` from the static board display list**

In the (now-replaced) board path there is no more `display_cols`; ensure no remaining reference to `"lr_tier"`. Search and confirm:

Run: `grep -n "lr_tier" views/draft_wizard.py`
Expected: no matches (the only remaining `lr_tier` references are the harmless `None`-fill in `_get_rookies`). If a display reference remains, delete it.

- [ ] **Step 4: Headless verify import + AppTest**

Run:
```bash
uv run python -c "
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('streamlit_app.py', default_timeout=30); at.run()
assert not at.exception, at.exception
print('OK')
"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add views/draft_wizard.py
git commit -m "feat(mock): mirror live cards/board in mock; phone-friendly grid; drop lr_tier"
```

---

## Task 10: Refresh + per-source freshness

**Files:**
- Modify: `tools/refresh_rankings.py` (fetch NFL draft)
- Modify: `components/sidebar.py` (`_refresh_data` + freshness lines)

- [ ] **Step 1: Add NFL draft to the CLI refresh**

In `tools/refresh_rankings.py`, after the KTC write and before/after matching, add NFL draft fetch. Insert after the `print("Fetching KeepTradeCut...")` block:

```python
    print("Fetching NFL draft capital...")
    from ingestion.nfl_draft import fetch_nfl_draft
    from config import NFL_DRAFT_PARQUET
    try:
        nd = fetch_nfl_draft()
        nd.to_parquet(NFL_DRAFT_PARQUET, index=False)
        print(f"  NFL draft: {len(nd)} skill picks")
    except Exception as e:
        print(f"  NFL draft fetch failed ({e}) — keeping existing file")
```

- [ ] **Step 2: Add NFL draft fetch + freshness to the sidebar refresh**

In `components/sidebar.py` `_refresh_data`, after the KTC block, add:

```python
        st.write("Fetching NFL draft capital...")
        try:
            from ingestion.nfl_draft import fetch_nfl_draft
            from config import NFL_DRAFT_PARQUET
            nd = fetch_nfl_draft()
            nd.to_parquet(NFL_DRAFT_PARQUET, index=False)
            st.write(f"NFL draft: {len(nd)} skill picks")
        except Exception as e:
            st.write(f"NFL draft fetch failed — keeping existing ({e})")
```

- [ ] **Step 3: Replace the single "Last refresh" caption with per-source freshness**

In `render_sidebar`, replace the `if MERGED_PARQUET.exists(): ... else: ...` freshness block with:

```python
    import os
    from datetime import datetime
    from config import FC_PARQUET, KTC_PARQUET, NFL_DRAFT_PARQUET, ADP_CSV
    from ingestion.lateround import LATEROUND_CSV

    def _fresh(path, label):
        if path.exists():
            ts = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%b %d %I:%M%p")
            try:
                import pandas as pd
                n = len(pd.read_parquet(path)) if str(path).endswith(".parquet") else len(pd.read_csv(path))
            except Exception:
                n = "?"
            st.sidebar.caption(f"{label}: {n} · {ts}")
        else:
            st.sidebar.caption(f"{label}: — (none)")

    _fresh(FC_PARQUET, "FantasyCalc")
    _fresh(KTC_PARQUET, "KeepTradeCut")
    _fresh(LATEROUND_CSV, "LateRound")
    _fresh(NFL_DRAFT_PARQUET, "NFL Draft")
    _fresh(ADP_CSV, "ADP")
```

- [ ] **Step 4: Verify CLI refresh writes NFL draft**

Run: `uv run python tools/refresh_rankings.py`
Expected: prints "NFL draft: ~80 skill picks" and rewrites parquets.

- [ ] **Step 5: Commit**

```bash
git add tools/refresh_rankings.py components/sidebar.py
git commit -m "feat(refresh): fetch NFL draft + per-source freshness in sidebar"
```

---

## Task 11: Seed snapshot + bootstrap

**Files:**
- Create: `ingestion/seed.py`
- Modify: `streamlit_app.py`, `.gitignore`
- Test: `tests/test_seed.py`
- Create data: `data/seed/*`

- [ ] **Step 1: Write failing test**

```python
# tests/test_seed.py
import pandas as pd
from ingestion import seed

def test_ensure_copies_missing(tmp_path, monkeypatch):
    data = tmp_path / "data"; seed_dir = data / "seed"
    seed_dir.mkdir(parents=True)
    (seed_dir / "merged.parquet").write_bytes(b"x")  # sentinel
    monkeypatch.setattr(seed, "DATA_DIR", data)
    monkeypatch.setattr(seed, "SEED_DIR", seed_dir)
    monkeypatch.setattr(seed, "SEED_FILES", ["merged.parquet"])
    seed.ensure_data_from_seed()
    assert (data / "merged.parquet").exists()

def test_does_not_overwrite_existing(tmp_path, monkeypatch):
    data = tmp_path / "data"; seed_dir = data / "seed"
    seed_dir.mkdir(parents=True)
    (seed_dir / "merged.parquet").write_bytes(b"SEED")
    (data / "merged.parquet").write_bytes(b"LIVE")
    monkeypatch.setattr(seed, "DATA_DIR", data)
    monkeypatch.setattr(seed, "SEED_DIR", seed_dir)
    monkeypatch.setattr(seed, "SEED_FILES", ["merged.parquet"])
    seed.ensure_data_from_seed()
    assert (data / "merged.parquet").read_bytes() == b"LIVE"  # unchanged
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_seed.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# ingestion/seed.py
"""Populate gitignored data/ from committed data/seed/ on a fresh clone (cloud)."""
import shutil

from config import DATA_DIR, SEED_DIR

SEED_FILES = [
    "fantasycalc.parquet", "ktc.parquet", "merged.parquet", "nfl_draft.parquet",
    "lateround_rankings.csv", "adp_rankings.csv",
]


def ensure_data_from_seed() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for fname in SEED_FILES:
        dst = DATA_DIR / fname
        src = SEED_DIR / fname
        if not dst.exists() and src.exists():
            shutil.copy(src, dst)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_seed.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Call bootstrap on startup**

In `streamlit_app.py`, add immediately after `import streamlit as st`:

```python
from ingestion.seed import ensure_data_from_seed
ensure_data_from_seed()
```

- [ ] **Step 6: Un-ignore the seed dir**

In `.gitignore`, replace the line `data/` with:

```
data/*
!data/seed/
```

- [ ] **Step 7: Create the seed snapshot from current fresh data**

Run:
```bash
mkdir -p data/seed
cp data/fantasycalc.parquet data/ktc.parquet data/merged.parquet data/nfl_draft.parquet data/lateround_rankings.csv data/adp_rankings.csv data/seed/
ls -1 data/seed
```
Expected: 6 files listed.

- [ ] **Step 8: Commit (seed data + bootstrap)**

```bash
git add .gitignore ingestion/seed.py tests/test_seed.py streamlit_app.py data/seed
git commit -m "feat(seed): commit ranking snapshot + bootstrap data/ from seed on cloud"
```

---

## Task 12: Streamlit Cloud deploy artifacts

**Files:**
- Create: `.streamlit/config.toml`, `requirements.txt`

- [ ] **Step 1: Theme/config**

Create `.streamlit/config.toml`:

```toml
[theme]
base = "dark"

[server]
headless = true
```

- [ ] **Step 2: Generate requirements.txt for Streamlit Cloud**

Run:
```bash
uv export --no-hashes --no-dev --format requirements-txt -o requirements.txt
head -20 requirements.txt
```
Expected: a requirements.txt containing streamlit, pandas, pyarrow, requests, beautifulsoup4, etc. (If `uv export` is unavailable, run `uv pip compile pyproject.toml -o requirements.txt`.)

- [ ] **Step 3: Final full headless verification**

Run:
```bash
uv run python -c "
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('streamlit_app.py', default_timeout=40); at.run()
assert not at.exception, at.exception
from views.draft_wizard import _get_rookies
r=_get_rookies('blended_rank')
assert len(r)>0 and r['blended_rank'].notna().any()
print('OK rookies', len(r))
"
uv run pytest tests/ -q
```
Expected: `OK rookies <n>`; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add .streamlit/config.toml requirements.txt
git commit -m "chore(deploy): streamlit config + requirements.txt for Streamlit Cloud"
```

- [ ] **Step 5: Deploy steps (manual, after merge to main)**

Documented for the operator (not an automated step):
1. Merge `feat/draft-app-upgrades` → `main`, push.
2. share.streamlit.io → New app → repo `stranger9977/dynasty-dashboard`, branch `main`, main file `streamlit_app.py`, Python 3.12.
3. No secrets needed. Deploy → open on phone → connect Sleeper user `brochillington` → league "Make it (dy)Nasty" → Draft Wizard.

---

## Self-Review notes

- **Spec coverage:** ADP (T4), NFL draft capital (T3), 5-source equal blend (T1,T5), LateRound-by-rank/drop tier (T5,T9), disagreement Spread + section (T1,T6,T8), best-available cards top 2–3 (T6,T8), live availability (T7,T8), mock mirrors live (T9), sortable mobile board + main-pane controls + decimal age (T6,T8), refresh/freshness (T10), seed+bootstrap (T11), deploy artifacts (T12). All covered.
- **Type consistency:** source keys `{lr,fc,ktc,draft,adp}` and columns `{lr_rank, fc_rookie_rank, ktc_rookie_rank, draft_skill_rank, adp_rank}` used identically in `blend.py`, `_get_rookies`, and `draft_board.py`. `attach_source_ranks(rookies, src, cols)` signature consistent across nfl_draft/adp.
- **Dropped (rolled back):** availability-probability model + manager tendency profiles — no tasks, by design.
