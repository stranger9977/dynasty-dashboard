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
