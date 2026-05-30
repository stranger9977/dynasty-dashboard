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
