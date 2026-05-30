# Draft Value Recap Implementation Plan (Phase A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Draft Recap" tab to the Rookie Draft Wizard that scores each manager's live-draft haul as surplus-vs-slot on an exponential-decay value curve, with source toggles, total + per-pick charts, reach/steal cards, and manager chips.

**Architecture:** A pure math module (`ingestion/draft_value.py`) holds the decay/surplus/aggregation functions (unit-tested, no Streamlit). A view module (`views/draft_value.py`) collects picks from the live Sleeper draft (mock fallback), runs the math, and renders charts/cards/chips. `_get_rookies` is extended to keep `__raw` per-source ranks so the recap blends on true source coverage. A third tab is wired into `views/draft_wizard.render()`.

**Tech Stack:** Python 3.12, pandas, Streamlit, pytest. Package manager: `uv` (run tests via `uv run pytest`).

**Spec:** `docs/superpowers/specs/2026-05-30-draft-value-recap-design.md`

---

## File Structure

- **Create `ingestion/draft_value.py`** — pure functions: `RAW_SOURCE_COLS`, `half_life_to_lambda`, `decay_value`, `consensus_rank`, `build_pick_values`, `summarize_managers`.
- **Create `views/draft_value.py`** — Streamlit UI: pick collection (`_collect_live_picks`, `_collect_mock_picks`, `_rookie_lookup`, `_source_ranks_from_row`), card/chip HTML (`_pick_card_html`, `_chip_html`), and the entry point `render_draft_value_recap`.
- **Create `tests/test_draft_value.py`** — pure-function unit tests.
- **Modify `views/draft_wizard.py`** — `_get_rookies` snapshots `__raw` source cols (~before line 77); `render()` adds the third tab (~line 577–584).
- **Modify `tests/test_get_rookies.py`** — assert `__raw` columns exist and preserve NaN.

All tasks assume the repo's local `data/merged.parquet` exists (the app runs locally), so `_get_rookies()` works in tests. Run tests with `uv run pytest`.

---

### Task 1: Decay value curve (`half_life_to_lambda`, `decay_value`)

**Files:**
- Create: `ingestion/draft_value.py`
- Test: `tests/test_draft_value.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_draft_value.py`:

```python
# tests/test_draft_value.py
import math
import pandas as pd
import pytest

from ingestion.draft_value import half_life_to_lambda, decay_value


def test_decay_value_rank_one_is_100():
    lam = half_life_to_lambda(6)
    assert decay_value(1, lam) == pytest.approx(100.0)


def test_decay_value_halves_at_half_life():
    lam = half_life_to_lambda(6)
    # rank 1 -> 100; rank (1 + half_life) -> half of that
    assert decay_value(1 + 6, lam) == pytest.approx(50.0)


def test_decay_value_strictly_decreasing():
    lam = half_life_to_lambda(6)
    vals = [decay_value(r, lam) for r in range(1, 20)]
    assert all(a > b for a, b in zip(vals, vals[1:]))


def test_decay_value_none_for_missing():
    lam = half_life_to_lambda(6)
    assert decay_value(None, lam) is None
    assert decay_value(float("nan"), lam) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_draft_value.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.draft_value'`

- [ ] **Step 3: Write minimal implementation**

Create `ingestion/draft_value.py`:

```python
# ingestion/draft_value.py
"""Pure value-curve + surplus + aggregation math for the Draft Value Recap.

A consensus rank maps to a draft value on an exponential-decay curve, so the
gap between elite picks dominates and late picks flatten toward zero. Surplus is
value(player) - value(slot). No Streamlit here — see views/draft_value.py."""
import math

import pandas as pd

from ingestion.blend import blend_rank

# logical source key -> the unfilled per-source rank column written by _get_rookies
RAW_SOURCE_COLS = {
    "lr": "lr_rank__raw",
    "fc": "fc_rookie_rank__raw",
    "ktc": "ktc_rookie_rank__raw",
    "draft": "draft_skill_rank__raw",
    "adp": "adp_rank__raw",
}


def half_life_to_lambda(half_life: float) -> float:
    """lambda such that value halves every `half_life` rank spots. half_life > 0."""
    return math.log(2) / half_life


def decay_value(rank, lam: float):
    """100 * exp(-lam * (rank - 1)). None/NaN -> None. rank >= 1 -> (0, 100]."""
    if rank is None or pd.isna(rank):
        return None
    return 100.0 * math.exp(-lam * (float(rank) - 1.0))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_draft_value.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/draft_value.py tests/test_draft_value.py
git commit -m "feat(draft-value): exponential decay value curve"
```

---

### Task 2: Consensus rank over active sources (`consensus_rank`)

**Files:**
- Modify: `ingestion/draft_value.py`
- Test: `tests/test_draft_value.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_draft_value.py`:

```python
from ingestion.draft_value import consensus_rank

SR = {"lr": 4, "fc": 14, "ktc": 12, "draft": 7, "adp": 5}


def test_consensus_equal_weight_all_active():
    got = consensus_rank(SR, {"lr", "fc", "ktc", "draft", "adp"})
    assert got == pytest.approx((4 + 14 + 12 + 7 + 5) / 5)


def test_consensus_ignores_inactive_source():
    # only lr, fc, draft active -> ktc & adp must not affect the blend
    got = consensus_rank(SR, {"lr", "fc", "draft"})
    assert got == pytest.approx((4 + 14 + 7) / 3)


def test_consensus_none_when_no_active_value():
    assert consensus_rank({"lr": None, "fc": None}, {"lr", "fc"}) is None


def test_consensus_single_source():
    assert consensus_rank(SR, {"adp"}) == 5


def test_consensus_active_source_missing_value_renormalizes():
    sr = {"lr": 4, "fc": None, "ktc": 12}
    assert consensus_rank(sr, {"lr", "fc", "ktc"}) == pytest.approx((4 + 12) / 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_draft_value.py -k consensus -v`
Expected: FAIL — `ImportError: cannot import name 'consensus_rank'`

- [ ] **Step 3: Write minimal implementation**

Append to `ingestion/draft_value.py`:

```python
def consensus_rank(source_ranks: dict, active, weights: dict | None = None):
    """Equal-weight (or weighted) blend of the *active* sources' ranks.

    source_ranks: {key: rank or None}. active: iterable of source keys to include.
    Returns the blended rank (float) or None if no active source has a value."""
    active = set(active)
    sr = {k: source_ranks.get(k) for k in active}
    w = {k: (weights.get(k, 1.0) if weights else 1.0) for k in active}
    return blend_rank(sr, w)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_draft_value.py -k consensus -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/draft_value.py tests/test_draft_value.py
git commit -m "feat(draft-value): consensus rank over active sources"
```

---

### Task 3: Per-pick surplus + manager aggregation (`build_pick_values`, `summarize_managers`)

**Files:**
- Modify: `ingestion/draft_value.py`
- Test: `tests/test_draft_value.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_draft_value.py`:

```python
from ingestion.draft_value import build_pick_values, summarize_managers


def _picks():
    return pd.DataFrame([
        {"manager": "A", "player": "P1", "position": "RB", "pick_no": 1,
         "consensus_rank": 1.0},    # rank == slot -> surplus 0
        {"manager": "B", "player": "P2", "position": "WR", "pick_no": 2,
         "consensus_rank": 10.0},   # rank 10 at slot 2 -> reach
        {"manager": "A", "player": "P3", "position": "QB", "pick_no": 12,
         "consensus_rank": 3.0},    # rank 3 at slot 12 -> steal
        {"manager": "B", "player": "P4", "position": "TE", "pick_no": 11,
         "consensus_rank": float("nan")},  # unranked -> reach
    ])


def test_surplus_zero_when_rank_equals_slot():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    assert df.loc[df["player"] == "P1", "surplus"].iloc[0] == pytest.approx(0.0)


def test_surplus_positive_for_steal():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    assert df.loc[df["player"] == "P3", "surplus"].iloc[0] > 0


def test_surplus_negative_for_reach():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    assert df.loc[df["player"] == "P2", "surplus"].iloc[0] < 0


def test_unranked_pick_is_reach():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    row = df.loc[df["player"] == "P4"].iloc[0]
    assert bool(row["unranked"]) is True
    assert row["surplus"] < 0


def test_summarize_aggregates_normalizes_and_sorts():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    s = summarize_managers(df)
    assert set(s.index) == {"A", "B"}
    for mgr in ("A", "B"):
        assert s.loc[mgr, "surplus_per_pick"] == pytest.approx(
            s.loc[mgr, "total_surplus"] / s.loc[mgr, "num_picks"])
    # A (one even pick + one steal) outranks B (two reaches)
    assert s.index[0] == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_draft_value.py -k "surplus or unranked or summarize" -v`
Expected: FAIL — `ImportError: cannot import name 'build_pick_values'`

- [ ] **Step 3: Write minimal implementation**

Append to `ingestion/draft_value.py`:

```python
def build_pick_values(picks: pd.DataFrame, lam: float, max_rank: float) -> pd.DataFrame:
    """Add value columns to a picks table.

    Required input columns: 'manager', 'player', 'position', 'pick_no',
    'consensus_rank' (float or NaN). Adds 'unranked' (bool), 'player_value',
    'slot_value', 'surplus'. A NaN consensus_rank is flagged unranked and filled
    with max_rank + 1 (worst) so it scores ~0 value -> a pure reach."""
    df = picks.copy()
    df["unranked"] = df["consensus_rank"].isna()
    filled = df["consensus_rank"].fillna(max_rank + 1)
    df["player_value"] = filled.apply(lambda r: decay_value(r, lam))
    df["slot_value"] = df["pick_no"].apply(lambda p: decay_value(p, lam))
    df["surplus"] = df["player_value"] - df["slot_value"]
    return df


def summarize_managers(pick_values: pd.DataFrame) -> pd.DataFrame:
    """Per-manager totals, indexed by manager and sorted by total_surplus desc.

    Columns: 'total_surplus', 'num_picks', 'surplus_per_pick'."""
    g = pick_values.groupby("manager")
    out = pd.DataFrame({
        "total_surplus": g["surplus"].sum(),
        "num_picks": g["surplus"].size(),
    })
    out["surplus_per_pick"] = out["total_surplus"] / out["num_picks"]
    return out.sort_values("total_surplus", ascending=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_draft_value.py -v`
Expected: PASS (all draft_value tests; 14 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/draft_value.py tests/test_draft_value.py
git commit -m "feat(draft-value): per-pick surplus + manager aggregation"
```

---

### Task 4: Keep unfilled `__raw` source ranks in `_get_rookies`

**Files:**
- Modify: `views/draft_wizard.py` (inside `_get_rookies`, just before the per-source NaN fill loop at ~line 77)
- Test: `tests/test_get_rookies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_get_rookies.py`:

```python
def test_get_rookies_keeps_raw_source_ranks():
    df = _get_rookies("blended_rank")
    for col in ["lr_rank", "fc_rookie_rank", "ktc_rookie_rank",
                "draft_skill_rank", "adp_rank"]:
        assert f"{col}__raw" in df.columns, f"{col}__raw"
    filled = pd.to_numeric(df["lr_rank"], errors="coerce")
    raw = pd.to_numeric(df["lr_rank__raw"], errors="coerce")
    # where raw has a value it equals the (pre-fill) value
    both = raw.notna()
    assert (raw[both] == filled[both]).all()
    # the fill changed something: some cells are filled numbers but raw is NaN
    assert (filled.notna() & raw.isna()).any()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_get_rookies.py::test_get_rookies_keeps_raw_source_ranks -v`
Expected: FAIL — `AssertionError: lr_rank__raw` (column missing)

- [ ] **Step 3: Write minimal implementation**

In `views/draft_wizard.py`, inside `_get_rookies`, insert the snapshot loop **immediately before** the existing comment `# Fill unranked (None/NaN) per-source ranks ...` (currently ~line 74). The existing fill block stays unchanged:

```python
    # Snapshot the TRUE (unfilled) per-source ranks so the Draft Recap can blend on
    # real source coverage (None when a source doesn't rank a player), not the
    # sort-sentinel written by the fill loop below.
    for col in ["lr_rank", "fc_rookie_rank", "ktc_rookie_rank",
                "draft_skill_rank", "adp_rank"]:
        if col in rookies.columns:
            rookies[f"{col}__raw"] = pd.to_numeric(rookies[col], errors="coerce")

    # Fill unranked (None/NaN) per-source ranks with (max + 1) so they sort to the
    # BOTTOM of a column-sorted table — Streamlit sorts nulls to the top otherwise.
    # Done AFTER the blend/spread above so those reflect true source coverage.
    for col in ["lr_rank", "fc_rookie_rank", "ktc_rookie_rank", "draft_skill_rank", "adp_rank"]:
        if col in rookies.columns:
            nums = pd.to_numeric(rookies[col], errors="coerce")
            if nums.notna().any():
                rookies[col] = nums.fillna(int(nums.max()) + 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_get_rookies.py -v`
Expected: PASS (3 passed — the two existing tests plus the new one)

- [ ] **Step 5: Commit**

```bash
git add views/draft_wizard.py tests/test_get_rookies.py
git commit -m "feat(draft-wizard): keep unfilled __raw source ranks for recap blend"
```

---

### Task 5: Draft Value Recap view (`views/draft_value.py`)

**Files:**
- Create: `views/draft_value.py`

This task has no new unit test (rendering is Streamlit-bound; it's exercised by the Task 6 AppTest smoke). Pure logic lives in `ingestion/draft_value.py` and is already tested.

- [ ] **Step 1: Create the view module**

Create `views/draft_value.py`:

```python
# views/draft_value.py
"""Draft Value Recap tab: surplus-vs-slot charts, reach/steal cards, and manager
chips driven by the live Sleeper draft (mock fallback). See the Phase A design doc."""
import pandas as pd
import streamlit as st

from ingestion.draft_value import (
    RAW_SOURCE_COLS, half_life_to_lambda, consensus_rank,
    build_pick_values, summarize_managers,
)
from ingestion.match_util import normalize_name

SOURCE_KEYS = ["lr", "fc", "ktc", "draft", "adp"]
SOURCE_LABELS = {"lr": "LR", "fc": "FC", "ktc": "KTC", "draft": "Draft", "adp": "ADP"}


def _rookie_lookup(rookies: pd.DataFrame):
    """(by_id, by_name) dicts mapping sleeper_id / normalized name -> rookie row dict."""
    by_id, by_name = {}, {}
    for _, r in rookies.iterrows():
        rec = r.to_dict()
        if pd.notna(r.get("sleeper_id")):
            by_id[str(r["sleeper_id"])] = rec
        by_name[normalize_name(str(r["name"]))] = rec
    return by_id, by_name


def _source_ranks_from_row(row: dict | None) -> dict:
    """Pull the five raw per-source ranks from a matched rookie row (None if absent)."""
    out = {}
    for k in SOURCE_KEYS:
        v = row.get(RAW_SOURCE_COLS[k]) if row else None
        out[k] = float(v) if (v is not None and pd.notna(v)) else None
    return out


def _collect_live_picks(rookies, draft, league_id):
    """Picks from the live Sleeper draft -> list of row dicts (or [] if none/error)."""
    from ingestion.sleeper import get_draft_picks, build_roster_to_manager
    try:
        picks = get_draft_picks(draft["draft_id"])
    except Exception:
        return []
    if not picks:
        return []
    roster_to_mgr = build_roster_to_manager(league_id) if league_id else {}
    by_id, by_name = _rookie_lookup(rookies)
    rows = []
    for pk in picks:
        md = pk.get("metadata") or {}
        nm = f"{md.get('first_name', '')} {md.get('last_name', '')}".strip()
        row = None
        if pk.get("player_id") and str(pk["player_id"]) in by_id:
            row = by_id[str(pk["player_id"])]
        elif nm:
            row = by_name.get(normalize_name(nm))
        rows.append({
            "manager": roster_to_mgr.get(pk.get("roster_id"), f"Team {pk.get('roster_id')}"),
            "player": (row or {}).get("name") or nm or "?",
            "position": (row or {}).get("position") or md.get("position") or "",
            "pick_no": pk.get("pick_no"),
            **_source_ranks_from_row(row),
        })
    return rows


def _collect_mock_picks(rookies):
    """Picks from the most recent in-session mock -> list of row dicts (or [])."""
    picks = st.session_state.get("draft_picks") or []
    if not picks:
        return []
    _, by_name = _rookie_lookup(rookies)
    rows = []
    for p in picks:
        row = by_name.get(normalize_name(str(p.get("player", ""))))
        rows.append({
            "manager": p.get("owner", "?"),
            "player": p.get("player", "?"),
            "position": p.get("player_pos") or (row or {}).get("position") or "",
            "pick_no": p.get("pick"),
            **_source_ranks_from_row(row),
        })
    return rows


def _pick_card_html(title, row, color):
    pos = row.get("position", "")
    rank = row.get("consensus_rank")
    rstr = f"{rank:.1f}" if pd.notna(rank) else "—"
    return (
        f"<div style='border:1px solid #444;border-left:5px solid {color};"
        f"border-radius:8px;padding:10px 12px;background:#1a1a2e'>"
        f"<div style='font-size:0.8em;color:#aaa'>{title}</div>"
        f"<div style='font-size:1.1em;font-weight:bold'>{row['player']} "
        f"<span style='color:#888;font-size:0.7em'>{pos}</span></div>"
        f"<div style='font-size:0.8em;color:#bbb'>{row['manager']} · "
        f"pick {row['pick_no']:.0f} · consensus {rstr}</div>"
        f"<div style='font-size:0.95em;color:{color}'>surplus {row['surplus']:+.0f}</div>"
        f"</div>"
    )


def _chip_html(title, manager, detail, color, avatar_url=None):
    """avatar_url is the deferred-avatar seam (Phase A leaves it None)."""
    avatar = (
        f"<img src='{avatar_url}' style='width:30px;height:30px;border-radius:50%;"
        f"margin-right:8px'>" if avatar_url else ""
    )
    return (
        f"<div style='display:flex;align-items:center;border:1px solid {color};"
        f"border-radius:16px;padding:8px 14px;background:#1a1a2e'>{avatar}"
        f"<div><div style='font-weight:bold;color:{color};font-size:0.85em'>{title}</div>"
        f"<div style='font-size:0.95em'>{manager}</div>"
        f"<div style='font-size:0.72em;color:#999'>{detail}</div></div></div>"
    )


def render_draft_value_recap(rookies, draft, league_id):
    st.subheader("Draft Recap — Value by Manager")

    rows, source_label = [], "live draft"
    if draft and draft.get("draft_id"):
        rows = _collect_live_picks(rookies, draft, league_id)
    if not rows:
        rows = _collect_mock_picks(rookies)
        source_label = "last mock"
    if not rows:
        st.info("No draft picks yet — start your live draft or run a mock "
                "in the Mock Draft Simulator to see the recap.")
        return

    picks_df = pd.DataFrame(rows)
    picks_df = picks_df[picks_df["pick_no"].notna()].copy()
    if picks_df.empty:
        st.info("No completed picks yet.")
        return

    st.caption(f"Based on the {source_label} · {len(picks_df)} picks · "
               "surplus = value of player taken − value of the slot used")

    # --- Controls: source toggles + decay half-life ---
    cols = st.columns(len(SOURCE_KEYS))
    active = set()
    for col, k in zip(cols, SOURCE_KEYS):
        if col.checkbox(SOURCE_LABELS[k], value=True, key=f"dvr_src_{k}"):
            active.add(k)
    if not active:
        st.warning("Select at least one ranking source.")
        return
    half_life = st.slider("Value half-life (picks)", 2, 15, 6, key="dvr_hl",
                          help="How fast pick value decays — lower means early "
                               "picks matter much more.")
    lam = half_life_to_lambda(half_life)

    # --- Math ---
    picks_df["consensus_rank"] = picks_df.apply(
        lambda r: consensus_rank({k: r[k] for k in SOURCE_KEYS}, active), axis=1)
    pv = build_pick_values(picks_df, lam, max_rank=len(rookies))
    summary = summarize_managers(pv)

    # --- Two charts side by side (stack on mobile) ---
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Total value vs slot**")
        st.bar_chart(summary["total_surplus"])
    with c2:
        st.markdown("**Value per pick**")
        st.bar_chart(summary["surplus_per_pick"])

    # --- Reach / Steal cards ---
    st.markdown("---")
    steal = pv.loc[pv["surplus"].idxmax()]
    reach = pv.loc[pv["surplus"].idxmin()]
    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown(_pick_card_html("💎 Biggest Steal", steal, "#4daf4a"),
                    unsafe_allow_html=True)
    with rc2:
        st.markdown(_pick_card_html("🧨 Biggest Reach", reach, "#e41a1c"),
                    unsafe_allow_html=True)

    # --- Manager chips ---
    st.markdown("---")
    hog = summary.index[0]       # highest total surplus
    guys = summary.index[-1]     # lowest total surplus
    hog_pick = pv[pv["manager"] == hog].sort_values("surplus", ascending=False).iloc[0]
    guys_pick = pv[pv["manager"] == guys].sort_values("surplus").iloc[0]
    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown(_chip_html(
            "🐷 Value Hog", hog,
            f"+{summary.loc[hog, 'total_surplus']:.0f} total · "
            f"best: {hog_pick['player']} ({hog_pick['surplus']:+.0f})",
            "#4daf4a"), unsafe_allow_html=True)
    with ch2:
        st.markdown(_chip_html(
            "🎯 Gets His Guys — no matter what", guys,
            f"{summary.loc[guys, 'total_surplus']:.0f} total · "
            f"reach: {guys_pick['player']} ({guys_pick['surplus']:+.0f})",
            "#e41a1c"), unsafe_allow_html=True)
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run python -c "import views.draft_value; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add views/draft_value.py
git commit -m "feat(draft-value): recap view — charts, reach/steal cards, chips"
```

---

### Task 6: Wire the "Draft Recap" tab + smoke test

**Files:**
- Modify: `views/draft_wizard.py` (`render()`, the tabs block at ~line 577–584)

- [ ] **Step 1: Add the third tab**

In `views/draft_wizard.py` `render()`, replace the two-tab block:

```python
    tab_board, tab_mock = st.tabs(["Draft Board", "Mock Draft Simulator"])

    with tab_board:
        _render_draft_board(rookies, available, rank_col, source_label, draft)

    with tab_mock:
        _render_mock_draft(rookies, draft_order, rank_col, num_teams,
                           num_rounds, user_slot, rules)
```

with:

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

- [ ] **Step 2: Write the AppTest smoke script**

Write `/tmp/verify_recap.py` (a one-time verification, not a committed test — connected path mirrors the repo's existing AppTest verifications and needs network for Sleeper):

```python
"""Verify the Draft Recap tab renders without exception against the connected
league, and that the mock-fallback path also renders."""
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


# Mock-fallback path: seed mock picks so the recap has data even with no live picks.
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
print("Recap header present:", "Value by Manager" in md)
print("Chips present:", "Value Hog" in md and "Gets His Guys" in md)
print("Cards present:", "Biggest Steal" in md and "Biggest Reach" in md)
ok = all(s in md for s in
         ["Value by Manager", "Value Hog", "Gets His Guys",
          "Biggest Steal", "Biggest Reach"])
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 3: Run the smoke + full suite**

Run: `uv run python /tmp/verify_recap.py`
Expected: prints `Recap header present: True`, `Chips present: True`, `Cards present: True`, `PASS`

Run: `uv run pytest -q`
Expected: PASS (all existing tests + the new `test_draft_value.py` + the new `test_get_rookies` case)

- [ ] **Step 4: Commit**

```bash
git add views/draft_wizard.py
git commit -m "feat(draft-wizard): wire Draft Recap tab"
```

---

## Final review

After all tasks, dispatch a final code review of the whole branch (`ingestion/draft_value.py`, `views/draft_value.py`, the `_get_rookies` and tab edits, tests), then use **superpowers:finishing-a-development-branch** to merge `draft-value-recap` into `main` (the user deploys Streamlit Cloud from `main`).
