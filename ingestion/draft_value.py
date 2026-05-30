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


def consensus_rank(source_ranks: dict, active, weights: dict | None = None):
    """Equal-weight (or weighted) blend of the *active* sources' ranks.

    source_ranks: {key: rank or None}. active: iterable of source keys to include.
    Returns the blended rank (float) or None if no active source has a value."""
    active = set(active)
    sr = {k: source_ranks.get(k) for k in active}
    w = {k: (weights.get(k, 1.0) if weights else 1.0) for k in active}
    return blend_rank(sr, w)


def build_pick_values(picks: pd.DataFrame, lam: float, max_rank: float) -> pd.DataFrame:
    """Add value columns to a picks table.

    Required input columns: 'manager', 'player', 'position', 'pick_no',
    'consensus_rank' (float or NaN). Adds 'unranked' (bool), 'player_value',
    'slot_value', 'surplus'. A NaN consensus_rank is flagged unranked and filled
    with max_rank + 1 (worst) so it scores ~0 value -> a pure reach."""
    df = picks.copy()
    # Coerce to numeric first so an all-None consensus column (object dtype) doesn't
    # trip pandas' deprecated object-downcast-on-fillna path.
    consensus = pd.to_numeric(df["consensus_rank"], errors="coerce")
    df["unranked"] = consensus.isna()
    filled = consensus.fillna(max_rank + 1)
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
