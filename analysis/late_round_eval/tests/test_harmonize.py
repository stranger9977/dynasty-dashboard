import json
from pathlib import Path
import pandas as pd
import pytest

from analysis.late_round_eval.extraction.harmonize import (
    apply_tier_map,
    build_harmonized_table,
    CANONICAL_TIERS,
)


def test_canonical_tiers_ordered():
    assert CANONICAL_TIERS == ["Elite", "Starter", "Flex", "Depth", "Dart Throw"]


def test_apply_tier_map_basic():
    rows = [
        {"guide_year": 2024, "name": "X", "position": "WR",
         "original_tier_label": "High-End Starter", "original_tier_rank": 2,
         "overall_rank": 1, "college": "C", "blurb": "b",
         "source_page": 1, "source_quote": "X"},
    ]
    tier_map = {"2024": {"High-End Starter": "Starter"}}
    result = apply_tier_map(rows, tier_map)
    assert result[0]["canonical_tier"] == "Starter"


def test_apply_tier_map_missing_mapping_raises():
    rows = [
        {"guide_year": 2024, "name": "X", "position": "WR",
         "original_tier_label": "Mystery Tier", "original_tier_rank": 1,
         "overall_rank": 1, "college": "C", "blurb": "b",
         "source_page": 1, "source_quote": "X"},
    ]
    tier_map = {"2024": {"Other Label": "Starter"}}
    with pytest.raises(KeyError, match="Mystery Tier"):
        apply_tier_map(rows, tier_map)


def test_build_harmonized_table(tmp_path):
    rows = [
        {"guide_year": 2024, "name": "A", "position": "WR",
         "original_tier_label": "Elite", "original_tier_rank": 1,
         "overall_rank": 1, "college": "C", "blurb": "b",
         "source_page": 1, "source_quote": "A"},
        {"guide_year": 2024, "name": "B", "position": "RB",
         "original_tier_label": "Dart Throw", "original_tier_rank": 5,
         "overall_rank": 50, "college": "C", "blurb": "b",
         "source_page": 50, "source_quote": "B"},
    ]
    tier_map = {"2024": {"Elite": "Elite", "Dart Throw": "Dart Throw"}}
    df = build_harmonized_table(rows, tier_map)
    assert len(df) == 2
    assert set(df["canonical_tier"]) == {"Elite", "Dart Throw"}
    # ordered factor
    assert df["canonical_tier"].dtype.name == "category"
