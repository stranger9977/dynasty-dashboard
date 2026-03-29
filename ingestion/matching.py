import re
from difflib import SequenceMatcher

import pandas as pd

from config import NAME_OVERRIDES

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_NON_ALPHA_RE = re.compile(r"[^a-z\s]")


def _normalize_name(name: str) -> str:
    n = name.lower().strip()
    n = _NON_ALPHA_RE.sub("", n)
    n = _SUFFIX_RE.sub("", n)
    return " ".join(n.split())


def merge_rankings(fc_df: pd.DataFrame, ktc_df: pd.DataFrame) -> pd.DataFrame:
    fc = fc_df.copy()
    kt = ktc_df.copy()

    # Ensure mfl_id is string for joining
    fc["mfl_id"] = fc["mfl_id"].astype(str).replace("nan", "")
    kt["mfl_id"] = kt["mfl_id"].astype(str).replace("nan", "")

    # Apply name overrides
    for fc_name, ktc_name in NAME_OVERRIDES.items():
        fc.loc[fc["name"] == fc_name, "name"] = ktc_name

    # --- Step 1: MFL ID join ---
    fc_with_mfl = fc[fc["mfl_id"] != ""].copy()
    kt_with_mfl = kt[kt["mfl_id"] != ""].copy()
    merged_mfl = fc_with_mfl.merge(
        kt_with_mfl, on="mfl_id", how="inner", suffixes=("_fc", "_ktc")
    )

    matched_fc_ids = set(merged_mfl["mfl_id"])
    fc_remaining = fc[~fc["mfl_id"].isin(matched_fc_ids) | (fc["mfl_id"] == "")]
    kt_remaining = kt[~kt["mfl_id"].isin(matched_fc_ids) | (kt["mfl_id"] == "")]

    # --- Step 2: Exact normalized name + position join ---
    fc_remaining = fc_remaining.copy()
    kt_remaining = kt_remaining.copy()
    fc_remaining["_norm"] = fc_remaining["name"].apply(_normalize_name)
    kt_remaining["_norm"] = kt_remaining["name"].apply(_normalize_name)
    fc_remaining["_key"] = fc_remaining["_norm"] + "|" + fc_remaining["position"]
    kt_remaining["_key"] = kt_remaining["_norm"] + "|" + kt_remaining["position"]

    merged_name = fc_remaining.merge(
        kt_remaining, on="_key", how="inner", suffixes=("_fc", "_ktc")
    )
    matched_keys = set(merged_name["_key"])
    fc_remaining = fc_remaining[~fc_remaining["_key"].isin(matched_keys)]
    kt_remaining = kt_remaining[~kt_remaining["_key"].isin(matched_keys)]

    # --- Step 3: Fuzzy name match (same position) ---
    fuzzy_matches = []
    for _, fc_row in fc_remaining.iterrows():
        candidates = kt_remaining[kt_remaining["position"] == fc_row["position"]]
        best_score, best_idx = 0.0, None
        for idx, kt_row in candidates.iterrows():
            score = SequenceMatcher(
                None, fc_row["_norm"], kt_row["_norm"]
            ).ratio()
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_score >= 0.85 and best_idx is not None:
            fuzzy_matches.append((fc_row.name, best_idx))
            kt_remaining = kt_remaining.drop(best_idx)

    merged_fuzzy_rows = []
    for fc_idx, kt_idx in fuzzy_matches:
        fc_row = fc_remaining.loc[fc_idx]
        kt_row = ktc_df.loc[kt_idx] if kt_idx in ktc_df.index else kt.loc[kt_idx]
        row = {}
        for col in fc_row.index:
            row[col + "_fc" if col in kt_row.index and col not in ("mfl_id",) else col] = fc_row[col]
        for col in kt_row.index:
            if col not in row:
                row[col + "_ktc" if col + "_fc" in row else col] = kt_row[col]
        merged_fuzzy_rows.append(row)

    fc_unmatched = fc_remaining.drop(
        [fc_idx for fc_idx, _ in fuzzy_matches], errors="ignore"
    )

    # --- Consolidate all matches into a uniform schema ---
    all_rows = []
    for source_df in [merged_mfl, merged_name]:
        for _, row in source_df.iterrows():
            all_rows.append(_unify_row(row))
    for row in merged_fuzzy_rows:
        all_rows.append(_unify_row(pd.Series(row)))

    # Add unmatched FC players
    for _, row in fc_unmatched.iterrows():
        all_rows.append(_unify_row_fc_only(row))

    # Add unmatched KTC players
    for _, row in kt_remaining.iterrows():
        all_rows.append(_unify_row_ktc_only(row))

    result = pd.DataFrame(all_rows)

    # Compute disagreement columns
    result["rank_diff"] = result["fc_rank"] - result["ktc_rank"]
    result["pos_rank_diff"] = result["fc_pos_rank"] - result["ktc_pos_rank"]
    result["rank_diff_abs"] = result["rank_diff"].abs()

    # Weighted disagreement: rank_diff / avg_rank
    # A 10-rank gap at rank 5 (~2.0) matters far more than at rank 300 (~0.03)
    result["avg_rank"] = (result["fc_rank"] + result["ktc_rank"]) / 2
    result["rank_diff_weighted"] = result["rank_diff"] / result["avg_rank"]
    result["rank_diff_weighted_abs"] = result["rank_diff_weighted"].abs()

    # Normalized value difference (0-100 scale)
    for col in ["fc_value", "ktc_value"]:
        cmin, cmax = result[col].min(), result[col].max()
        if cmax > cmin:
            result[col + "_norm"] = (result[col] - cmin) / (cmax - cmin) * 100
        else:
            result[col + "_norm"] = 50.0
    result["value_diff_norm"] = result["fc_value_norm"] - result["ktc_value_norm"]

    result = result.sort_values("rank_diff_weighted_abs", ascending=False, na_position="last")
    result = result.reset_index(drop=True)
    return result


def _unify_row(row) -> dict:
    def _pick(key_fc, key_ktc, fallback=None):
        v = row.get(key_fc)
        if pd.isna(v) if not isinstance(v, str) else v == "":
            v = row.get(key_ktc, fallback)
        return v

    return {
        "name": _pick("name_fc", "name_ktc", _pick("name", "name")),
        "position": _pick("position_fc", "position_ktc", _pick("position", "position")),
        "team": _pick("team_fc", "team_ktc", _pick("team", "team")),
        "age": _pick("age_fc", "age_ktc", _pick("age", "age")),
        "years_exp": _pick("years_exp_fc", "years_exp_ktc", _pick("years_exp", "years_exp")),
        "is_rookie": _pick("is_rookie_fc", "is_rookie_ktc", _pick("is_rookie", "is_rookie")),
        "sleeper_id": row.get("sleeper_id", row.get("sleeper_id_fc")),
        "mfl_id": row.get("mfl_id", row.get("mfl_id_fc")),
        "ktc_id": row.get("ktc_id", row.get("ktc_id_ktc")),
        "fc_value": row.get("fc_value", row.get("fc_value_fc")),
        "fc_rank": row.get("fc_rank", row.get("fc_rank_fc")),
        "fc_pos_rank": row.get("fc_pos_rank", row.get("fc_pos_rank_fc")),
        "fc_tier": row.get("fc_tier", row.get("fc_tier_fc")),
        "fc_trend_30d": row.get("fc_trend_30d", row.get("fc_trend_30d_fc")),
        "fc_redraft_value": row.get("fc_redraft_value", row.get("fc_redraft_value_fc")),
        "ktc_value": row.get("ktc_value", row.get("ktc_value_ktc")),
        "ktc_rank": row.get("ktc_rank", row.get("ktc_rank_ktc")),
        "ktc_pos_rank": row.get("ktc_pos_rank", row.get("ktc_pos_rank_ktc")),
        "ktc_tier": row.get("ktc_tier", row.get("ktc_tier_ktc")),
        "college": row.get("college", row.get("college_ktc")),
        "draft_year": row.get("draft_year", row.get("draft_year_ktc")),
    }


def _unify_row_fc_only(row) -> dict:
    return {
        "name": row.get("name"),
        "position": row.get("position"),
        "team": row.get("team"),
        "age": row.get("age"),
        "years_exp": row.get("years_exp"),
        "is_rookie": row.get("is_rookie"),
        "sleeper_id": row.get("sleeper_id"),
        "mfl_id": row.get("mfl_id"),
        "ktc_id": None,
        "fc_value": row.get("fc_value"),
        "fc_rank": row.get("fc_rank"),
        "fc_pos_rank": row.get("fc_pos_rank"),
        "fc_tier": row.get("fc_tier"),
        "fc_trend_30d": row.get("fc_trend_30d"),
        "fc_redraft_value": row.get("fc_redraft_value"),
        "ktc_value": None, "ktc_rank": None, "ktc_pos_rank": None, "ktc_tier": None,
        "college": None, "draft_year": None,
    }


def _unify_row_ktc_only(row) -> dict:
    return {
        "name": row.get("name"),
        "position": row.get("position"),
        "team": row.get("team"),
        "age": row.get("age"),
        "years_exp": row.get("years_exp"),
        "is_rookie": row.get("is_rookie"),
        "sleeper_id": None,
        "mfl_id": row.get("mfl_id"),
        "ktc_id": row.get("ktc_id"),
        "fc_value": None, "fc_rank": None, "fc_pos_rank": None, "fc_tier": None,
        "fc_trend_30d": None, "fc_redraft_value": None,
        "ktc_value": row.get("ktc_value"),
        "ktc_rank": row.get("ktc_rank"),
        "ktc_pos_rank": row.get("ktc_pos_rank"),
        "ktc_tier": row.get("ktc_tier"),
        "college": row.get("college"),
        "draft_year": row.get("draft_year"),
    }
