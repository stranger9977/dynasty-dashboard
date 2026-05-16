"""Birthday-anchored matcher with stage-by-stage relaxation."""
from typing import Callable
import pandas as pd
from rapidfuzz import fuzz

from analysis.late_round_eval.extraction.enrich_birthdays import normalize_name


def _candidate_join(
    guide: pd.DataFrame,
    nfl: pd.DataFrame,
    keys: list[tuple[str, str]],
    fuzzy_name: bool = False,
    fuzzy_threshold: float = 0.85,
) -> pd.DataFrame:
    """Join guide -> nfl using `keys` (each tuple = (guide_col, nfl_col)).

    If fuzzy_name is True, the name pair (first tuple) is matched via SequenceMatcher
    ratio >= fuzzy_threshold instead of exact equality.
    """
    rows = []
    for _, g in guide.iterrows():
        for _, n in nfl.iterrows():
            ok = True
            score = None
            for i, (gcol, ncol) in enumerate(keys):
                gv, nv = g[gcol], n[ncol]
                if pd.isna(gv) or pd.isna(nv):
                    ok = False
                    break
                if i == 0 and fuzzy_name:
                    score = fuzz.ratio(normalize_name(str(gv)), normalize_name(str(nv))) / 100.0
                    if score < fuzzy_threshold:
                        ok = False
                        break
                else:
                    if i == 0:
                        if normalize_name(str(gv)) != normalize_name(str(nv)):
                            ok = False
                            break
                    else:
                        if gv != nv:
                            ok = False
                            break
            if ok:
                # Guide columns take precedence over NFL columns on name collisions
                # so downstream dedup keys (name, position) refer to the guide row.
                merged = {**n.to_dict(), **g.to_dict()}
                merged["fuzzy_score"] = score if score is not None else 1.0
                rows.append(merged)
    return pd.DataFrame(rows)


def stage_1_exact_name_position_birthday(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("birthday", "birth_date")],
        fuzzy_name=False,
    )
    out["match_stage"] = 1
    return out


def stage_2_normalized_name_position_birthday(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("birthday", "birth_date")],
        fuzzy_name=False,
    )
    out["match_stage"] = 2
    return out


def stage_3_fuzzy_name_position_birthday(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("birthday", "birth_date")],
        fuzzy_name=True,
        fuzzy_threshold=0.85,
    )
    out["match_stage"] = 3
    return out


def stage_4_exact_name_position_year_college(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"),
              ("guide_year", "draft_year"), ("college", "college")],
        fuzzy_name=False,
    )
    out["match_stage"] = 4
    return out


def stage_5_fuzzy_name_position_year_college(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"),
              ("guide_year", "draft_year"), ("college", "college")],
        fuzzy_name=True,
        fuzzy_threshold=0.85,
    )
    out["match_stage"] = 5
    return out


def stage_6_fuzzy_name_position_year(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("guide_year", "draft_year")],
        fuzzy_name=True,
        fuzzy_threshold=0.80,
    )
    out["match_stage"] = 6
    return out


STAGES: list[tuple[int, Callable]] = [
    (1, stage_1_exact_name_position_birthday),
    (2, stage_2_normalized_name_position_birthday),
    (3, stage_3_fuzzy_name_position_birthday),
    (4, stage_4_exact_name_position_year_college),
    (5, stage_5_fuzzy_name_position_year_college),
    (6, stage_6_fuzzy_name_position_year),
]


def run_funnel(
    guide: pd.DataFrame,
    nfl: pd.DataFrame,
    auditor_fn: Callable | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run all stages sequentially, removing matched players after each stage.

    If auditor_fn is provided, it's called with (stage_num, candidates_df) and
    returns a DataFrame of confirmed false positives. Confirmed FPs are removed
    from accepted matches.

    Returns (all_matches, unmatched_guide_rows).
    """
    remaining = guide.copy().reset_index(drop=True)
    all_matches: list[pd.DataFrame] = []
    for stage_num, fn in STAGES:
        if remaining.empty:
            break
        candidates = fn(remaining, nfl)
        if candidates.empty:
            continue
        if auditor_fn is not None:
            fps = auditor_fn(stage_num, candidates)
            if not fps.empty:
                fp_keys = set(zip(fps["name"], fps["position"]))
                candidates = candidates[
                    ~candidates.apply(lambda r: (r["name"], r["position"]) in fp_keys, axis=1)
                ]
        all_matches.append(candidates)
        matched_names = set(zip(candidates["name"], candidates["position"]))
        remaining = remaining[
            ~remaining.apply(lambda r: (r["name"], r["position"]) in matched_names, axis=1)
        ].reset_index(drop=True)

    matches = pd.concat(all_matches, ignore_index=True) if all_matches else pd.DataFrame()
    return matches, remaining
