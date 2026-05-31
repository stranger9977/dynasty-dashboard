# tests/test_roster_impact.py
import pandas as pd
import pytest

from ingestion.roster_impact import starter_points, points_above_starters

COUNTS = {"QB": 2, "RB": 3, "WR": 4, "TE": 2}


def _df(rows):
    # rows: list of (position, pts)
    return pd.DataFrame(rows, columns=["position", "pts"])


def test_starter_points_top_n_per_position():
    # 3 QBs, take top 2 -> 300 + 250
    df = _df([("QB", 300), ("QB", 250), ("QB", 200)])
    assert starter_points(df, COUNTS, "pts") == pytest.approx(550)


def test_starter_points_multi_position_sum():
    df = _df([("QB", 300), ("QB", 250), ("RB", 100), ("RB", 90), ("RB", 80),
              ("RB", 70), ("WR", 50), ("TE", 40)])
    # QB top2: 550 ; RB top3: 270 ; WR top4: 50 ; TE top2: 40 -> 910
    assert starter_points(df, COUNTS, "pts") == pytest.approx(910)


def test_starter_points_fewer_than_n_sums_available():
    df = _df([("QB", 300)])                 # only 1 QB though counts asks 2
    assert starter_points(df, COUNTS, "pts") == pytest.approx(300)


def test_above_starters_upgrade_is_marginal():
    base = _df([("QB", 300), ("QB", 250)])  # both QB slots filled
    add = _df([("QB", 280)])                # cracks lineup, benches the 250
    # new top2 = 300 + 280 = 580 ; old = 550 -> +30
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(30)


def test_above_starters_below_cutoff_is_zero():
    base = _df([("QB", 300), ("QB", 250)])
    add = _df([("QB", 150)])                # worse than worst starter -> no change
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(0)


def test_above_starters_two_rookies_displace_two_starters():
    base = _df([("RB", 100), ("RB", 90), ("RB", 80)])   # top3 = 270
    add = _df([("RB", 110), ("RB", 95)])                # new top3 = 110+100+95=305
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(35)


def test_above_starters_empty_added_is_zero():
    base = _df([("QB", 300), ("QB", 250)])
    add = pd.DataFrame(columns=["position", "pts"])
    assert points_above_starters(base, add, COUNTS, "pts") == pytest.approx(0)


# --- lineup_changes: per-position +/- breakdown ---
from ingestion.roster_impact import lineup_changes


def _idf(rows):
    # rows: (player_id, position, pts, name)
    return pd.DataFrame(rows, columns=["player_id", "position", "pts", "name"])


def test_lineup_changes_swap_in_and_out():
    base = _idf([("v1", "QB", 300, "Vet A"), ("v2", "QB", 250, "Vet B")])
    add = _idf([("r1", "QB", 280, "Rook")])
    qb = lineup_changes(base, add, COUNTS, "pts")["QB"]
    assert qb["delta"] == pytest.approx(30)
    assert qb["added_in"] == [("Rook", 280.0)]
    assert qb["bumped_out"] == [("Vet B", 250.0)]
    assert ("Rook", 280.0) in qb["new_starters"]
    assert qb["old_starters"] == [("Vet A", 300.0), ("Vet B", 250.0)]


def test_lineup_changes_below_cutoff_no_swap():
    base = _idf([("v1", "QB", 300, "A"), ("v2", "QB", 250, "B")])
    add = _idf([("r1", "QB", 150, "R")])
    qb = lineup_changes(base, add, COUNTS, "pts")["QB"]
    assert qb["delta"] == pytest.approx(0)
    assert qb["added_in"] == []
    assert qb["bumped_out"] == []


def test_lineup_changes_fills_open_slot():
    # only 1 QB rostered but 2 start -> rookie fills the open slot, nobody bumped
    base = _idf([("v1", "QB", 300, "A")])
    add = _idf([("r1", "QB", 120, "R")])
    qb = lineup_changes(base, add, COUNTS, "pts")["QB"]
    assert qb["delta"] == pytest.approx(120)
    assert qb["added_in"] == [("R", 120.0)]
    assert qb["bumped_out"] == []


def test_lineup_changes_deltas_sum_to_points_above_starters():
    base = _idf([("v1", "RB", 100, "A"), ("v2", "RB", 90, "B"),
                 ("v3", "RB", 80, "C"), ("w1", "WR", 50, "D")])
    add = _idf([("r1", "RB", 110, "X"), ("r2", "WR", 60, "Y")])
    res = lineup_changes(base, add, COUNTS, "pts")
    total = sum(p["delta"] for p in res.values())
    assert total == pytest.approx(points_above_starters(base, add, COUNTS, "pts"))
