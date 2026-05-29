# ingestion/match_util.py
"""Shared name normalization + fuzzy source-rank attachment (name + position)."""
import re
from difflib import SequenceMatcher

import pandas as pd

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_NON_ALPHA_RE = re.compile(r"[^a-z\s]")


def normalize_name(name) -> str:
    n = str(name).lower().strip()
    n = _NON_ALPHA_RE.sub("", n)
    n = _SUFFIX_RE.sub("", n)
    return " ".join(n.split())


def attach_source_ranks(rookies: pd.DataFrame, src: pd.DataFrame,
                        cols: list[str], threshold: float = 0.80) -> pd.DataFrame:
    """Left-attach src[cols] onto rookies by normalized name+position (exact then
    fuzzy). Each src row used at most once. Adds `cols` (None where unmatched)."""
    rookies = rookies.copy()
    for c in cols:
        rookies[c] = None
    if src is None or src.empty:
        return rookies

    rookies["_norm"] = rookies["name"].apply(normalize_name)
    src = src.copy()
    src["_norm"] = src["name"].apply(normalize_name)
    used: set = set()

    # Pass 1: exact normalized name + position
    for r_idx, r in rookies.iterrows():
        m = src[(src["_norm"] == r["_norm"]) & (src["position"] == r["position"])
                & (~src.index.isin(used))]
        if len(m) >= 1:
            s_idx = m.index[0]
            used.add(s_idx)
            for c in cols:
                rookies.at[r_idx, c] = src.at[s_idx, c]

    # Pass 2: fuzzy for still-unmatched rookies (same position)
    unmatched = rookies[rookies[cols[0]].isna()]
    for r_idx, r in unmatched.iterrows():
        cands = src[(~src.index.isin(used)) & (src["position"] == r["position"])]
        best, best_idx = 0.0, None
        for s_idx, s in cands.iterrows():
            score = SequenceMatcher(None, r["_norm"], s["_norm"]).ratio()
            if score > best:
                best, best_idx = score, s_idx
        if best >= threshold and best_idx is not None:
            used.add(best_idx)
            for c in cols:
                rookies.at[r_idx, c] = src.at[best_idx, c]

    return rookies.drop(columns=["_norm"], errors="ignore")
