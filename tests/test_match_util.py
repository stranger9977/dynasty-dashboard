# tests/test_match_util.py
import pandas as pd
from ingestion.match_util import normalize_name, attach_source_ranks

def test_normalize_strips_suffix_and_punct():
    assert normalize_name("Omar Cooper Jr.") == "omar cooper"
    assert normalize_name("Ja'Marr Chase") == "jamarr chase"

def test_attach_exact_and_fuzzy():
    rookies = pd.DataFrame([
        {"name": "Omar Cooper Jr.", "position": "WR"},
        {"name": "Jeremiyah Love", "position": "RB"},
        {"name": "Nobody Here", "position": "TE"},
    ])
    src = pd.DataFrame([
        {"name": "Omar Cooper", "position": "WR", "adp_rank": 9},   # exact after normalize
        {"name": "Jeremiah Love", "position": "RB", "adp_rank": 1}, # fuzzy (one letter)
    ])
    out = attach_source_ranks(rookies, src, ["adp_rank"])
    assert out.loc[0, "adp_rank"] == 9
    assert out.loc[1, "adp_rank"] == 1
    assert pd.isna(out.loc[2, "adp_rank"])

def test_attach_empty_source_adds_null_cols():
    rookies = pd.DataFrame([{"name": "X", "position": "WR"}])
    out = attach_source_ranks(rookies, pd.DataFrame(), ["adp_rank"])
    assert "adp_rank" in out.columns and pd.isna(out.loc[0, "adp_rank"])
