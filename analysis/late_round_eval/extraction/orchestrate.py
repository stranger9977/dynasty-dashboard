"""Aggregation, validation, and spot-check report generation for extraction output."""
import json
import random
from pathlib import Path
from pydantic import ValidationError

from analysis.late_round_eval.extraction.schemas import GuidePlayer
from analysis.late_round_eval.extraction.validate import source_quote_in_dump


def load_and_validate_extraction(players_path: str) -> tuple[list[dict], list[dict]]:
    """Load player rows from JSON and validate against GuidePlayer schema.

    Returns (valid_rows_as_dicts, dropped_rows_as_dicts). Dropped rows include
    the original payload plus a `_validation_error` field.
    """
    raw = json.loads(Path(players_path).read_text())
    valid: list[dict] = []
    dropped: list[dict] = []
    for row in raw:
        try:
            GuidePlayer(**row)
            valid.append(row)
        except ValidationError as e:
            dropped.append({**row, "_validation_error": str(e)})
    return valid, dropped


def validate_against_dump(rows: list[dict], dump_path: str) -> tuple[list[dict], list[dict]]:
    """Filter rows whose source_quote fuzzy-matches into the PDF text dump.

    Returns (verified, unverified).
    """
    dump = Path(dump_path).read_text()
    verified, unverified = [], []
    for row in rows:
        if source_quote_in_dump(row["source_quote"], dump, threshold=0.95):
            verified.append(row)
        else:
            unverified.append({**row, "_reason": "source_quote not found in dump"})
    return verified, unverified


def build_spot_check_report(rows: list[dict], samples_per_year: int = 10, seed: int = 42) -> str:
    """Build a markdown report sampling N rows per year for human review."""
    rng = random.Random(seed)
    lines = ["# Extraction Spot-Check Report",
             "",
             "Each row shows extracted name | tier | source_quote | page. ",
             "Verify the source_quote actually appears on the listed page in the PDF.",
             ""]
    by_year: dict[int, list[dict]] = {}
    for r in rows:
        by_year.setdefault(r["guide_year"], []).append(r)
    for year in sorted(by_year):
        lines.append(f"## {year}")
        lines.append("")
        lines.append("| Name | Position | Tier | Page | Source Quote |")
        lines.append("|---|---|---|---|---|")
        sample = rng.sample(by_year[year], min(samples_per_year, len(by_year[year])))
        for r in sample:
            q = r["source_quote"].replace("|", "\\|")
            lines.append(f"| {r['name']} | {r['position']} | {r['original_tier_label']} | {r['source_page']} | {q} |")
        lines.append("")
    return "\n".join(lines)
