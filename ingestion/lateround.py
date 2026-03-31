import re
from difflib import SequenceMatcher

import pandas as pd

from config import DATA_DIR

LATEROUND_CSV = DATA_DIR / "lateround_rankings.csv"

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_NON_ALPHA_RE = re.compile(r"[^a-z\s]")


def _normalize(name: str) -> str:
    n = name.lower().strip()
    n = _NON_ALPHA_RE.sub("", n)
    n = _SUFFIX_RE.sub("", n)
    return " ".join(n.split())


def load_lateround() -> pd.DataFrame:
    if not LATEROUND_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(LATEROUND_CSV)
    df = df.rename(columns={
        "rank": "lr_rank",
        "pos_rank": "lr_pos_rank",
        "tier": "lr_tier",
    })
    return df


def merge_lateround(rookies: pd.DataFrame, lr: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy-match LateRound rankings onto the rookies dataframe."""
    if lr.empty:
        return rookies

    rookies = rookies.copy()
    rookies["_norm"] = rookies["name"].apply(_normalize)

    lr = lr.copy()
    lr["_norm"] = lr["name"].apply(_normalize)

    # Build match: lr name -> rookies index
    lr_rank_map = {}  # rookies index -> lr row
    used_lr = set()

    # Pass 1: exact normalized name + position
    for lr_idx, lr_row in lr.iterrows():
        matches = rookies[
            (rookies["_norm"] == lr_row["_norm"]) &
            (rookies["position"] == lr_row["position"])
        ]
        if len(matches) == 1:
            lr_rank_map[matches.index[0]] = lr_row
            used_lr.add(lr_idx)

    # Pass 2: fuzzy match remaining
    unmatched_lr = lr[~lr.index.isin(used_lr)]
    matched_rookie_idx = set(lr_rank_map.keys())

    for lr_idx, lr_row in unmatched_lr.iterrows():
        candidates = rookies[
            (~rookies.index.isin(matched_rookie_idx)) &
            (rookies["position"] == lr_row["position"])
        ]
        best_score, best_idx = 0.0, None
        for r_idx, r_row in candidates.iterrows():
            score = SequenceMatcher(None, lr_row["_norm"], r_row["_norm"]).ratio()
            if score > best_score:
                best_score = score
                best_idx = r_idx
        if best_score >= 0.80 and best_idx is not None:
            lr_rank_map[best_idx] = lr_row
            matched_rookie_idx.add(best_idx)

    # Apply LR columns
    rookies["lr_rank"] = None
    rookies["lr_pos_rank"] = None
    rookies["lr_tier"] = None

    for r_idx, lr_row in lr_rank_map.items():
        rookies.at[r_idx, "lr_rank"] = lr_row["lr_rank"]
        rookies.at[r_idx, "lr_pos_rank"] = lr_row["lr_pos_rank"]
        rookies.at[r_idx, "lr_tier"] = lr_row["lr_tier"]

    rookies = rookies.drop(columns=["_norm"], errors="ignore")
    return rookies
