import pytest
from pydantic import ValidationError
from analysis.late_round_eval.extraction.schemas import GuidePlayer, GuideMetadata


def test_guide_player_valid():
    p = GuidePlayer(
        guide_year=2024,
        name="Ladd McConkey",
        position="WR",
        original_tier_label="High-End Starter",
        original_tier_rank=2,
        overall_rank=14,
        college="Georgia",
        blurb="Polished route runner...",
        source_page=23,
        source_quote="2. Ladd McConkey, WR, Georgia",
    )
    assert p.name == "Ladd McConkey"
    assert p.position == "WR"


def test_guide_player_invalid_position():
    with pytest.raises(ValidationError):
        GuidePlayer(
            guide_year=2024,
            name="X",
            position="OL",  # not allowed
            original_tier_label="X",
            original_tier_rank=1,
            overall_rank=1,
            college="X",
            blurb="X",
            source_page=1,
            source_quote="X",
        )


def test_guide_player_missing_source_quote_rejected():
    with pytest.raises(ValidationError):
        GuidePlayer(
            guide_year=2024,
            name="X",
            position="WR",
            original_tier_label="X",
            original_tier_rank=1,
            overall_rank=1,
            college="X",
            blurb="X",
            source_page=1,
            # source_quote missing
        )


def test_guide_player_blurb_max_length():
    with pytest.raises(ValidationError):
        GuidePlayer(
            guide_year=2024,
            name="X",
            position="WR",
            original_tier_label="X",
            original_tier_rank=1,
            overall_rank=1,
            college="X",
            blurb="x" * 501,  # exceeds 500
            source_page=1,
            source_quote="X",
        )


def test_guide_metadata_valid():
    m = GuideMetadata(
        guide_year=2024,
        version="Post-Draft V2",
        methodology_text="We use breakout age and dominator...",
        features_mentioned=["age", "breakout age", "dominator"],
        tier_definitions={"Elite": "Top of the class", "Starter": "Likely producer"},
    )
    assert m.guide_year == 2024
