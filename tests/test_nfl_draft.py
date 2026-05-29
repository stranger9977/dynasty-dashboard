# tests/test_nfl_draft.py
import pandas as pd
from ingestion.nfl_draft import _compute_draft_ranks

def _raw():
    return pd.DataFrame([
        {"season": 2026, "pick": 1, "team": "LVR", "pfr_player_name": "Fernando Mendoza", "position": "QB", "college": "Indiana"},
        {"season": 2026, "pick": 2, "team": "X", "pfr_player_name": "Some Tackle", "position": "T", "college": "Y"},
        {"season": 2026, "pick": 3, "team": "ARI", "pfr_player_name": "Jeremiyah Love", "position": "RB", "college": "ND"},
        {"season": 2026, "pick": 4, "team": "TEN", "pfr_player_name": "Carnell Tate", "position": "WR", "college": "OSU"},
        {"season": 2026, "pick": 13, "team": "LAR", "pfr_player_name": "Ty Simpson", "position": "QB", "college": "Bama"},
        {"season": 2025, "pick": 1, "team": "Z", "pfr_player_name": "Old Guy", "position": "WR", "college": "Z"},
    ])

def test_skill_filter_and_overall_skill_rank():
    out = _compute_draft_ranks(_raw(), 2026)
    assert list(out["name"]) == ["Fernando Mendoza", "Jeremiyah Love", "Carnell Tate", "Ty Simpson"]
    assert list(out["draft_skill_rank"]) == [1, 2, 3, 4]
    assert "Some Tackle" not in set(out["name"])
    assert "Old Guy" not in set(out["name"])

def test_positional_rank_by_pick():
    out = _compute_draft_ranks(_raw(), 2026)
    qbs = out[out["position"] == "QB"].sort_values("draft_overall_pick")
    assert list(qbs["draft_pos_rank"]) == [1, 2]

def test_empty_when_season_absent():
    out = _compute_draft_ranks(_raw(), 2099)
    assert out.empty
    assert set(["name", "draft_skill_rank", "draft_pos_rank"]).issubset(out.columns)
