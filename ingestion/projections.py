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
