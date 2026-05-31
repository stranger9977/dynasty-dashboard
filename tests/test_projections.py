# tests/test_projections.py
import pandas as pd

from ingestion.projections import _parse_projections, OUT_COLS

SAMPLE = [
    {"player_id": "4984",
     "player": {"first_name": "Josh", "last_name": "Allen", "position": "QB",
                "team": "BUF", "years_exp": 8},
     "stats": {"pts_ppr": 361.5, "pts_half_ppr": 361.5, "pts_std": 361.5}},
    {"player_id": "13287",
     "player": {"first_name": "Jeremiyah", "last_name": "Love", "position": "RB",
                "team": "FA", "years_exp": 0},
     "stats": {"pts_ppr": 239.0, "pts_half_ppr": 220.0, "pts_std": 200.0}},
    {"player_id": "999",
     "player": {"first_name": "Some", "last_name": "Kicker", "position": "K",
                "team": "NE", "years_exp": 3},
     "stats": {"pts_ppr": 150.0}},                       # non-skill -> dropped
    {"player_id": "888",
     "player": {"first_name": "No", "last_name": "Proj", "position": "WR",
                "team": "NE", "years_exp": 2},
     "stats": {"pts_ppr": None}},                        # null pts -> dropped
]


def test_parse_keeps_only_skill_with_pts():
    df = _parse_projections(SAMPLE)
    assert list(df.columns) == OUT_COLS
    assert len(df) == 2                                  # Allen + Love only
    assert set(df["position"]) <= {"QB", "RB", "WR", "TE"}


def test_parse_player_id_is_string_and_name_joined():
    df = _parse_projections(SAMPLE)
    row = df[df["player_id"] == "4984"].iloc[0]
    assert isinstance(row["player_id"], str)
    assert row["name"] == "Josh Allen"


def test_parse_sorted_by_pts_ppr_desc():
    df = _parse_projections(SAMPLE)
    assert df.iloc[0]["name"] == "Josh Allen"            # 361.5 before 239.0
    assert list(df["pts_ppr"]) == sorted(df["pts_ppr"], reverse=True)


def test_parse_empty_input():
    df = _parse_projections([])
    assert list(df.columns) == OUT_COLS
    assert df.empty


def test_parse_drops_duplicate_player_ids():
    dup = [
        {"player_id": "7", "player": {"first_name": "Dup", "last_name": "Guy",
            "position": "WR", "team": "NE", "years_exp": 1}, "stats": {"pts_ppr": 100.0}},
        {"player_id": "7", "player": {"first_name": "Dup", "last_name": "Guy",
            "position": "WR", "team": "NE", "years_exp": 1}, "stats": {"pts_ppr": 100.0}},
    ]
    df = _parse_projections(dup)
    assert len(df) == 1
    assert df.set_index("player_id").index.is_unique
