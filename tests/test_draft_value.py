# tests/test_draft_value.py
import math
import pandas as pd
import pytest

from ingestion.draft_value import half_life_to_lambda, decay_value


def test_decay_value_rank_one_is_100():
    lam = half_life_to_lambda(6)
    assert decay_value(1, lam) == pytest.approx(100.0)


def test_decay_value_halves_at_half_life():
    lam = half_life_to_lambda(6)
    # rank 1 -> 100; rank (1 + half_life) -> half of that
    assert decay_value(1 + 6, lam) == pytest.approx(50.0)


def test_decay_value_strictly_decreasing():
    lam = half_life_to_lambda(6)
    vals = [decay_value(r, lam) for r in range(1, 20)]
    assert all(a > b for a, b in zip(vals, vals[1:]))


def test_decay_value_none_for_missing():
    lam = half_life_to_lambda(6)
    assert decay_value(None, lam) is None
    assert decay_value(float("nan"), lam) is None


from ingestion.draft_value import consensus_rank

SR = {"lr": 4, "fc": 14, "ktc": 12, "draft": 7, "adp": 5}


def test_consensus_equal_weight_all_active():
    got = consensus_rank(SR, {"lr", "fc", "ktc", "draft", "adp"})
    assert got == pytest.approx((4 + 14 + 12 + 7 + 5) / 5)


def test_consensus_ignores_inactive_source():
    # only lr, fc, draft active -> ktc & adp must not affect the blend
    got = consensus_rank(SR, {"lr", "fc", "draft"})
    assert got == pytest.approx((4 + 14 + 7) / 3)


def test_consensus_none_when_no_active_value():
    assert consensus_rank({"lr": None, "fc": None}, {"lr", "fc"}) is None


def test_consensus_single_source():
    assert consensus_rank(SR, {"adp"}) == 5


def test_consensus_active_source_missing_value_renormalizes():
    sr = {"lr": 4, "fc": None, "ktc": 12}
    assert consensus_rank(sr, {"lr", "fc", "ktc"}) == pytest.approx((4 + 12) / 2)


from ingestion.draft_value import build_pick_values, summarize_managers


def _picks():
    return pd.DataFrame([
        {"manager": "A", "player": "P1", "position": "RB", "pick_no": 1,
         "consensus_rank": 1.0},    # rank == slot -> surplus 0
        {"manager": "B", "player": "P2", "position": "WR", "pick_no": 2,
         "consensus_rank": 10.0},   # rank 10 at slot 2 -> reach
        {"manager": "A", "player": "P3", "position": "QB", "pick_no": 12,
         "consensus_rank": 3.0},    # rank 3 at slot 12 -> steal
        {"manager": "B", "player": "P4", "position": "TE", "pick_no": 11,
         "consensus_rank": float("nan")},  # unranked -> reach
    ])


def test_surplus_zero_when_rank_equals_slot():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    assert df.loc[df["player"] == "P1", "surplus"].iloc[0] == pytest.approx(0.0)


def test_surplus_positive_for_steal():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    assert df.loc[df["player"] == "P3", "surplus"].iloc[0] > 0


def test_surplus_negative_for_reach():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    assert df.loc[df["player"] == "P2", "surplus"].iloc[0] < 0


def test_unranked_pick_is_reach():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    row = df.loc[df["player"] == "P4"].iloc[0]
    assert bool(row["unranked"]) is True
    assert row["surplus"] < 0


def test_summarize_aggregates_normalizes_and_sorts():
    lam = half_life_to_lambda(6)
    df = build_pick_values(_picks(), lam, max_rank=60)
    s = summarize_managers(df)
    assert set(s.index) == {"A", "B"}
    for mgr in ("A", "B"):
        assert s.loc[mgr, "surplus_per_pick"] == pytest.approx(
            s.loc[mgr, "total_surplus"] / s.loc[mgr, "num_picks"])
    # A (one even pick + one steal) outranks B (two reaches)
    assert s.index[0] == "A"
