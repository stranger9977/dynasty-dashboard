# tests/test_adp.py
import pandas as pd
from ingestion.adp import merge_adp, _rename_adp

def test_rename_columns():
    raw = pd.DataFrame([{"rank": 1, "name": "A", "position": "RB", "pos_rank": 1, "adp": 1.1}])
    out = _rename_adp(raw)
    assert {"adp_rank", "adp_pos_rank", "adp_value"}.issubset(out.columns)
    assert out.loc[0, "adp_rank"] == 1 and out.loc[0, "adp_value"] == 1.1

def test_merge_adp_onto_rookies():
    rookies = pd.DataFrame([{"name": "Carnell Tate", "position": "WR"}])
    adp = pd.DataFrame([{"adp_rank": 2, "name": "Carnell Tate", "position": "WR", "adp_pos_rank": 1, "adp_value": 2.6}])
    out = merge_adp(rookies, adp)
    assert out.loc[0, "adp_rank"] == 2 and out.loc[0, "adp_value"] == 2.6
