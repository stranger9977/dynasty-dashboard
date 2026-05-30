# tests/test_get_rookies.py
import pandas as pd
from views.draft_wizard import _get_rookies, RANK_SOURCES


def test_get_rookies_has_all_source_ranks_and_blend():
    df = _get_rookies("blended_rank")
    assert len(df) > 0
    for col in ["blended_rank", "rank_spread", "adp_rank", "draft_skill_rank",
                "fc_rookie_rank", "ktc_rookie_rank", "lr_rank"]:
        assert col in df.columns, col
    assert df.iloc[0]["blended_rank"] is not None
    assert df["rank_spread"].notna().any()
    assert "source_high" in df.columns and "source_low" in df.columns


def test_rank_sources_resolve_to_columns():
    df = _get_rookies("blended_rank")
    for label, col in RANK_SOURCES.items():
        assert col in df.columns, f"{label}->{col}"


def test_get_rookies_keeps_raw_source_ranks():
    df = _get_rookies("blended_rank")
    for col in ["lr_rank", "fc_rookie_rank", "ktc_rookie_rank",
                "draft_skill_rank", "adp_rank"]:
        assert f"{col}__raw" in df.columns, f"{col}__raw"
    filled = pd.to_numeric(df["lr_rank"], errors="coerce")
    raw = pd.to_numeric(df["lr_rank__raw"], errors="coerce")
    # where raw has a value it equals the (pre-fill) value
    both = raw.notna()
    assert (raw[both] == filled[both]).all()
    # the fill changed something: some cells are filled numbers but raw is NaN
    assert (filled.notna() & raw.isna()).any()
