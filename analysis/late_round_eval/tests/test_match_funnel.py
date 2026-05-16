import pandas as pd
import pytest

from analysis.late_round_eval.extraction.match_funnel import (
    stage_1_exact_name_position_birthday,
    stage_3_fuzzy_name_position_birthday,
    stage_5_fuzzy_name_position_year_college,
    run_funnel,
)


GUIDE = pd.DataFrame([
    {"name": "Ladd McConkey", "position": "WR", "guide_year": 2024,
     "birthday": "2001-11-02", "college": "Georgia"},
    {"name": "Jamar Chase", "position": "WR", "guide_year": 2021,
     "birthday": "2000-03-01", "college": "LSU"},  # nickname for Ja'Marr Chase
    {"name": "Mystery Player", "position": "RB", "guide_year": 2024,
     "birthday": None, "college": "Nowhere State"},
])

NFL = pd.DataFrame([
    {"player_id": "P1", "name": "Ladd McConkey", "position": "WR",
     "birth_date": "2001-11-02", "draft_year": 2024, "college": "Georgia"},
    {"player_id": "P2", "name": "Ja'Marr Chase", "position": "WR",
     "birth_date": "2000-03-01", "draft_year": 2021, "college": "LSU"},
])


def test_stage_1_matches_exact_birthday():
    matched = stage_1_exact_name_position_birthday(GUIDE, NFL)
    assert len(matched) == 1
    assert matched.iloc[0]["player_id"] == "P1"


def test_stage_3_fuzzy_name_matches_nickname():
    # After stage 1, Ja'Marr / Jamar shouldn't match exactly
    remaining = GUIDE.iloc[[1, 2]].reset_index(drop=True)
    matched = stage_3_fuzzy_name_position_birthday(remaining, NFL)
    assert len(matched) == 1
    assert matched.iloc[0]["name"] == "Jamar Chase"
    assert matched.iloc[0]["player_id"] == "P2"
    assert matched.iloc[0]["fuzzy_score"] >= 0.85


def test_run_funnel_unmatched_goes_to_review():
    matches, unmatched = run_funnel(GUIDE, NFL, auditor_fn=None)
    # First two match, third doesn't
    assert len(matches) == 2
    assert len(unmatched) == 1
    assert unmatched.iloc[0]["name"] == "Mystery Player"


def test_run_funnel_invokes_auditor_per_stage():
    calls = []
    def fake_auditor(stage_num, candidates):
        calls.append((stage_num, len(candidates)))
        return pd.DataFrame()  # no false positives
    matches, unmatched = run_funnel(GUIDE, NFL, auditor_fn=fake_auditor)
    # Auditor was called for each stage that produced new candidates
    assert len(calls) >= 1
    assert all(c[1] > 0 for c in calls)
