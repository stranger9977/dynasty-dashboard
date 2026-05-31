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
