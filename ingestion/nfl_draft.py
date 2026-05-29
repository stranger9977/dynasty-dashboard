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
