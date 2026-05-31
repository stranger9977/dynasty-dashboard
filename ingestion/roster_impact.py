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
