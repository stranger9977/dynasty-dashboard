import json
from pathlib import Path
from analysis.late_round_eval.extraction.orchestrate import (
    load_and_validate_extraction,
    build_spot_check_report,
)


def test_load_and_validate_drops_invalid_rows(tmp_path):
    players = [
        {
            "guide_year": 2024, "name": "Ladd McConkey", "position": "WR",
            "original_tier_label": "Starter", "original_tier_rank": 2,
            "overall_rank": 14, "college": "Georgia", "blurb": "x",
            "source_page": 23, "source_quote": "2. Ladd McConkey, WR, Georgia",
        },
        {
            "guide_year": 2024, "name": "Bad Row", "position": "WR",
            "original_tier_label": "Starter", "original_tier_rank": 1,
            "overall_rank": 1, "college": "X", "blurb": "x",
            "source_page": 1,
            # source_quote missing — should be dropped
        },
    ]
    players_path = tmp_path / "players.json"
    players_path.write_text(json.dumps(players))

    valid, dropped = load_and_validate_extraction(str(players_path))
    assert len(valid) == 1
    assert valid[0]["name"] == "Ladd McConkey"
    assert len(dropped) == 1


def test_spot_check_report_includes_10_rows_per_year(tmp_path):
    # Build a fake aggregated dataset with 50 rows per year, 3 years
    rows = []
    for year in [2022, 2023, 2024]:
        for i in range(50):
            rows.append({
                "guide_year": year, "name": f"Player {year}-{i}", "position": "WR",
                "original_tier_label": "Starter", "original_tier_rank": 2,
                "overall_rank": i + 1, "college": "X", "blurb": "x",
                "source_page": i + 1, "source_quote": f"Player {year}-{i}",
            })
    md = build_spot_check_report(rows, samples_per_year=10, seed=42)
    for year in [2022, 2023, 2024]:
        assert f"## {year}" in md
    # 30 sample lines total
    assert md.count("| ") >= 30
