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
