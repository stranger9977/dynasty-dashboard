# tests/test_blend.py
import pytest
from ingestion.blend import blend_rank, rank_spread

def test_blend_equal_weights_all_present():
    sr = {"lr": 4, "fc": 14, "ktc": 12, "draft": 7, "adp": 5}
    w = {k: 0.2 for k in sr}
    assert blend_rank(sr, w) == pytest.approx((4 + 14 + 12 + 7 + 5) / 5)  # 8.4

def test_blend_renormalizes_missing_source():
    sr = {"lr": 4, "fc": 14, "ktc": 12, "draft": 7, "adp": None}
    w = {k: 0.2 for k in sr}
    assert blend_rank(sr, w) == pytest.approx((4 + 14 + 12 + 7) / 4)  # 9.25

def test_blend_none_when_no_sources():
    assert blend_rank({"lr": None, "fc": None}, {"lr": 0.5, "fc": 0.5}) is None

def test_blend_respects_unequal_weights():
    sr = {"lr": 10, "fc": 20}
    assert blend_rank(sr, {"lr": 0.75, "fc": 0.25}) == 10 * 0.75 + 20 * 0.25  # 12.5

def test_rank_spread_basic():
    sr = {"lr": 3, "fc": 14, "ktc": 12, "draft": 7, "adp": 5}
    spread, high, low = rank_spread(sr)
    assert spread == 14 - 3
    assert high == "lr"   # most bullish = lowest rank number
    assert low == "fc"    # most bearish = highest rank number

def test_rank_spread_needs_two_sources():
    assert rank_spread({"lr": 3, "fc": None}) == (None, None, None)
