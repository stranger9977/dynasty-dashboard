# Draft Value Recap — Design (Phase A)

**Date:** 2026-05-30
**Status:** Approved for planning
**Scope:** Phase A of a two-phase Draft Wizard expansion. Phase A (this doc) is the
**Draft Value Recap**: a value-by-manager chart, reach/steal cards, and manager chips,
all driven by the **live Sleeper draft** (with a mock fallback). Phase B (separate
spec/plan, later) adds 2026 FantasyPros projections and the "points added / points above
your starters" views.

---

## Goal

Give the user, during their live rookie draft, an at-a-glance read of **who is winning
the draft** — how much value each manager is getting relative to where they picked —
plus the single biggest steal and reach, and two playful manager chips.

## Background / current state

- The Draft Wizard (`views/draft_wizard.py`) already loads rookies via `_get_rookies()`
  with a blended rank and five per-source ranks (LR / FC / KTC / NFL Draft / ADP).
- Live draft picks are available via `ingestion/sleeper.get_draft_picks(draft_id)`
  (cached `ttl=30`). Each pick has `round`, `roster_id`, `player_id`, `picked_by`,
  `pick_no` (overall), `draft_slot`, and `metadata{first_name, last_name, position, ...}`.
- `ingestion/sleeper.build_roster_to_manager(league_id)` returns `{roster_id: name}`.
- `ingestion/blend.blend_rank(source_ranks, weights)` already does a renormalized
  weighted mean over present sources — reused here for source toggles.
- `ingestion/match_util.normalize_name(name)` is the shared name normalizer.
- Tests are pure-function unit tests under `tests/test_*.py` (see `tests/test_blend.py`).

## Non-goals (Phase A)

- No projections / points (Phase B).
- No Sleeper avatars on chips yet — a deferred nice-to-have; the chip renderer leaves a
  clean seam (`avatar_url` arg defaulting to `None`).
- No new persisted data files; the recap is computed live from the draft + existing
  rookie ranks.

---

## The value model

Each consensus rank is mapped to a **draft value** on an exponential-decay curve so the
gap between elite picks dominates and late picks flatten toward zero:

```
λ          = ln(2) / half_life          # half_life in "rank spots"
value(r)   = 100 · exp( −λ · (r − 1) )   # r >= 1  →  (0, 100]
```

- `half_life` is user-controlled via a **"Value half-life (picks)"** slider, default **6**
  (range 2–15). With half-life 6: value(1)=100, value(7)≈50, value(13)≈25, value(48)≈0.5.
- For each actual pick:
  - `player_value = value(consensus_rank_of_player)`
  - `slot_value   = value(overall_pick_no_used)`
  - **`surplus = player_value − slot_value`**
    - `surplus > 0` → **steal** (player better than the slot).
    - `surplus < 0` → **reach**.
- `pick_no` (1..~60) and consensus rank (1..~60) share the same scale, so picking the #N
  consensus player at slot N gives surplus 0 by construction.
- A drafted player present in **none** of the active ranking sources gets a consensus rank
  of `max_rank + 1` (≈0 value) → counts as a pure reach.

### Source toggles

Checkboxes for **LR / FC / KTC / NFL Draft / ADP** (all on by default). A player's
consensus rank is an **equal-weight blend of the checked sources only**, via `blend_rank`
with weight `1.0` per active source. This answers "who won the draft by ADP?" or
"…ignoring KTC?".

To blend honestly, the recap needs the **true** per-source ranks (None when a source
doesn't rank a player), not the sort-sentinel that `_get_rookies` writes (it fills
unranked cells with `max+1` so they sort last in tables). Fix: `_get_rookies` snapshots the
raw numeric per-source ranks into `{col}__raw` columns *before* the fill. The recap reads
the `__raw` columns; existing table/sort behavior is unchanged.

---

## Architecture

Two new files + small edits, mirroring the existing `ingestion/` (pure) vs `views/` (UI)
split.

### `ingestion/draft_value.py` — pure, no Streamlit

```python
import math
import pandas as pd
from ingestion.blend import blend_rank

RAW_SOURCE_COLS = {            # logical key -> __raw column written by _get_rookies
    "lr": "lr_rank__raw",
    "fc": "fc_rookie_rank__raw",
    "ktc": "ktc_rookie_rank__raw",
    "draft": "draft_skill_rank__raw",
    "adp": "adp_rank__raw",
}

def half_life_to_lambda(half_life: float) -> float:
    """λ such that value halves every `half_life` rank spots. half_life>0."""
    return math.log(2) / half_life

def decay_value(rank, lam: float):
    """100·exp(−λ·(rank−1)). None/NaN rank -> None. rank>=1 -> (0,100]."""
    if rank is None or (isinstance(rank, float) and math.isnan(rank)):
        return None
    return 100.0 * math.exp(-lam * (float(rank) - 1.0))

def consensus_rank(source_ranks: dict, active, weights: dict | None = None):
    """Equal-weight (or weighted) blend of the *active* sources' ranks.
    source_ranks: {key: rank or None}. active: iterable of keys to include.
    Returns blended rank (float) or None if no active source has a value."""
    active = set(active)
    sr = {k: source_ranks.get(k) for k in active}
    w = {k: (weights.get(k, 1.0) if weights else 1.0) for k in active}
    return blend_rank(sr, w)

def build_pick_values(picks: pd.DataFrame, lam: float, max_rank: float) -> pd.DataFrame:
    """Add value columns to a picks table.

    Input columns required: 'manager', 'player', 'position', 'pick_no',
    'consensus_rank' (float or NaN).
    Adds: 'player_value', 'slot_value', 'surplus', 'unranked' (bool).
    Missing consensus_rank -> filled with max_rank+1 (worst) and flagged unranked."""
    df = picks.copy()
    df["unranked"] = df["consensus_rank"].isna()
    filled = df["consensus_rank"].fillna(max_rank + 1)
    df["player_value"] = filled.apply(lambda r: decay_value(r, lam))
    df["slot_value"] = df["pick_no"].apply(lambda p: decay_value(p, lam))
    df["surplus"] = df["player_value"] - df["slot_value"]
    return df

def summarize_managers(pick_values: pd.DataFrame) -> pd.DataFrame:
    """Per-manager totals. Returns df indexed by manager with columns
    'total_surplus', 'num_picks', 'surplus_per_pick', sorted by total desc."""
    g = pick_values.groupby("manager")
    out = pd.DataFrame({
        "total_surplus": g["surplus"].sum(),
        "num_picks": g["surplus"].size(),
    })
    out["surplus_per_pick"] = out["total_surplus"] / out["num_picks"]
    return out.sort_values("total_surplus", ascending=False)
```

### `views/draft_value.py` — Streamlit UI

`render_draft_value_recap(rookies, draft, league_id)`:

1. **Collect picks** into a normalized table `[manager, player, position, pick_no, lr, fc,
   ktc, draft, adp]` (the five raw per-source ranks):
   - **Live** (preferred): `get_draft_picks(draft["draft_id"])`. Map `roster_id →
     manager` via `build_roster_to_manager(league_id)`. Resolve each pick to a rookie row
     by `sleeper_id == player_id`, else by `normalize_name(metadata first+last)`. Pull the
     five `__raw` ranks + position from the matched rookie row (fall back to metadata
     position; ranks None if unmatched). `pick_no` from the pick.
   - **Fallback** (no live draft / 0 picks): `st.session_state["draft_picks"]` from the
     mock — each has `player`, `owner`, `pick`. Match `player` name → rookie row for the
     five raw ranks; `manager = owner`, `pick_no = pick`.
   - If neither has picks → `st.info("No draft picks yet — start your live draft or run a
     mock to see the recap.")` and return.
2. **Controls** (main pane, mobile-first): five source checkboxes (default on); the value
   half-life slider (default 6). `active = {checked keys}`; `lam =
   half_life_to_lambda(half_life)`.
3. Compute `consensus_rank` per row over `active`, then `build_pick_values(...,
   max_rank=len(rookies))`, then `summarize_managers(...)`.
4. **Two charts side by side** via `st.columns(2)` (stack on mobile):
   - left: `st.bar_chart(summary["total_surplus"])` — "Total value vs slot".
   - right: `st.bar_chart(summary["surplus_per_pick"])` — "Value per pick" (the
     picks-count normalization).
5. **Reach / Steal cards** (`st.columns(2)`): steal = row at `surplus.idxmax()`, reach =
   row at `surplus.idxmin()`. Each card shows manager, player, `POS`, `slot used`,
   `consensus rank`, and the surplus (HTML card matching the existing card style in
   `views/draft_board.py`).
6. **Chips** via `_chip_html(title, manager, detail, color, avatar_url=None)`:
   - 🐷 **Value Hog** → `summary` top row (highest `total_surplus`); detail = their biggest
     single steal.
   - 🎯 **Gets His Guys — no matter what** → `summary` bottom row (lowest `total_surplus`);
     detail = their biggest single reach.
   - `avatar_url` arg is the deferred-avatar seam (unused in Phase A).

### Edits to existing files

- **`views/draft_wizard.py`**
  - `_get_rookies`: before the per-source NaN fill loop, write `__raw` snapshots:
    ```python
    for col in ["lr_rank", "fc_rookie_rank", "ktc_rookie_rank",
                "draft_skill_rank", "adp_rank"]:
        if col in rookies.columns:
            rookies[f"{col}__raw"] = pd.to_numeric(rookies[col], errors="coerce")
    ```
  - `render()`: third tab.
    ```python
    tab_board, tab_mock, tab_recap = st.tabs(
        ["Draft Board", "Mock Draft Simulator", "Draft Recap"])
    ...
    with tab_recap:
        from views.draft_value import render_draft_value_recap
        render_draft_value_recap(
            rookies, draft, st.session_state.get("league_id", ""))
    ```

---

## Testing

`tests/test_draft_value.py` (pure, mirrors `tests/test_blend.py`):

- `decay_value(1, λ) == 100`; strictly decreasing in rank; `decay_value(1+half_life, λ) ≈ 50`
  for `λ = half_life_to_lambda(half_life)`; None/NaN → None.
- `consensus_rank`: equal-weight average of active sources; an inactive source's rank is
  ignored even when present; returns None when no active source has a value; respects a
  single active source (returns that rank).
- `build_pick_values`: surplus sign — player ranked **better** (lower) than the pick slot →
  `surplus > 0`; equal rank == slot → `surplus == 0`; a row with NaN consensus_rank is
  flagged `unranked` and yields `surplus < 0` (reach).
- `summarize_managers`: `surplus_per_pick == total_surplus / num_picks`; sorted by
  `total_surplus` descending; multi-pick manager aggregates correctly.

A light Streamlit `AppTest` smoke (mock-fallback path) confirms the Draft Recap tab renders
without exception when a mock has run.

---

## Risks / decisions

- **Decay scale is cosmetic** beyond ordering; the half-life slider lets the user tune
  "how much do early picks matter." Default 6 chosen so the top ~13 ranks carry most of the
  signal in a 5-round / 60-pick rookie draft.
- **Unmatched live picks** (player not in the rookie pool — e.g. a non-rookie taken, or a
  name mismatch) get None ranks → treated as unranked reaches. Acceptable; name matching
  reuses the same normalizer the rest of the app trusts.
- **Surplus, not talent**, is the headline (user decision) so the chart, cards, and chips
  all share one "beat your slot" meaning.

## Phase B (future, separate spec)

FantasyPros 2026 projections → ID/fuzzy merge across all rosters (must not drop notable
names) → "total projected points added to roster" + "projected points above **your own**
starters (top 2 QB / 4 WR / 3 RB / 2 TE)" views. The projections fetch + merge will be
de-risked at the start of that phase.
