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
    if added.empty:
        return 0.0
    # Concat only non-empty frames so an empty baseline/added doesn't trip pandas'
    # deprecated all-NA concatenation path.
    frames = [f for f in (baseline, added) if not f.empty]
    combined = pd.concat(frames, ignore_index=True)
    return (starter_points(combined, counts, score_col)
            - starter_points(baseline, counts, score_col))


def lineup_changes(baseline: pd.DataFrame, added: pd.DataFrame,
                   counts: dict | None = None, score_col: str = "pts",
                   id_col: str = "player_id", name_col: str = "name") -> dict:
    """Per-position breakdown of how `added` changes the starting lineup.

    Returns {position: {
        'delta': float,                          # points the lineup gained at this slot
        'old_starters': [(name, pts), ...],      # current (pre-add) starters — veterans
        'new_starters': [(name, pts), ...],      # starters after adding
        'added_in':    [(name, pts), ...],       # entered the lineup (the '+')
        'bumped_out':  [(name, pts), ...],       # pushed out of the lineup (the '−')
        'upgrades':    [{'player','pts','replaced','replaced_pts','gain'}, ...],
    }}. Each upgrade is one entrant credited (best first) against the weakest
    starter it pushes out (replaced=None for an open slot); upgrade gains sum to
    delta. Identity is by id_col so same-named players don't collide. Both frames
    need 'position', score_col, id_col, and name_col columns."""
    counts = counts or STARTER_COUNTS

    def _pairs(df):
        return [(str(r[name_col]), float(r[score_col])) for _, r in df.iterrows()]

    result = {}
    for pos, n in counts.items():
        base_pos = baseline[baseline["position"] == pos]
        add_pos = added[added["position"] == pos]
        old = base_pos.sort_values(score_col, ascending=False).head(n)
        frames = [f for f in (base_pos, add_pos) if not f.empty]
        combined = pd.concat(frames, ignore_index=True) if frames else base_pos
        new = combined.sort_values(score_col, ascending=False).head(n)
        old_ids, new_ids = set(old[id_col]), set(new[id_col])
        entrants = _pairs(new[~new[id_col].isin(old_ids)])   # new is score-desc
        bumped = _pairs(old[~old[id_col].isin(new_ids)])     # old is score-desc
        # Credit the best entrant against the weakest starter it pushes out, so an
        # individual "upgrade" reflects the elite pickup (gains still sum to delta).
        bumped_asc = sorted(bumped, key=lambda t: t[1])
        upgrades = []
        for i, (nm, pts) in enumerate(entrants):
            rep_nm, rep_pts = bumped_asc[i] if i < len(bumped_asc) else (None, 0.0)
            upgrades.append({"player": nm, "pts": pts, "replaced": rep_nm,
                             "replaced_pts": rep_pts, "gain": pts - rep_pts})
        result[pos] = {
            "delta": float(new[score_col].sum() - old[score_col].sum()),
            "old_starters": _pairs(old),
            "new_starters": _pairs(new),
            "added_in": entrants,
            "bumped_out": bumped,
            "upgrades": upgrades,
        }
    return result
