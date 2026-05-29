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
