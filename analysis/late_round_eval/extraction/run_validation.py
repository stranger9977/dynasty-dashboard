"""Run validation across all 5 extraction outputs. Writes spot-check report."""
import json
from pathlib import Path

from analysis.late_round_eval.extraction.orchestrate import (
    load_and_validate_extraction,
    validate_against_dump,
    build_spot_check_report,
)


def main():
    output_dir = Path("analysis/late_round_eval/extraction/output")
    dump_dir = Path("analysis/late_round_eval/guides/text_dumps")
    all_verified: list[dict] = []
    summary: list[dict] = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        players_path = output_dir / f"{year}_players.json"
        if not players_path.exists():
            print(f"MISSING: {players_path}")
            continue
        valid, dropped_schema = load_and_validate_extraction(str(players_path))
        verified, unverified = validate_against_dump(valid, str(dump_dir / f"{year}_dump.txt"))
        all_verified.extend(verified)
        summary.append({
            "year": year, "raw": len(valid) + len(dropped_schema),
            "schema_valid": len(valid), "dump_verified": len(verified),
            "dropped_schema": len(dropped_schema), "unverified_quote": len(unverified),
        })
        # Persist unverified for review
        unverified_path = output_dir / f"{year}_unverified.json"
        unverified_path.write_text(json.dumps(dropped_schema + unverified, indent=2))

    print("\nValidation summary:")
    for s in summary:
        print(f"  {s['year']}: raw={s['raw']} valid={s['schema_valid']} verified={s['dump_verified']}")

    review = build_spot_check_report(all_verified)
    (output_dir / "extraction_review.md").write_text(review)
    print(f"\nSpot-check report: {output_dir / 'extraction_review.md'}")
    print("REVIEW THIS FILE BEFORE PROCEEDING TO TASK 5.")


if __name__ == "__main__":
    main()
