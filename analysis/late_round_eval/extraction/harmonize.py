"""Tier harmonization: per-year labels → canonical 5-tier scheme.

Also extracts the per-player ZAP score (a 0-100 model output) from the
source_quote when present. ZAP scores appear in 2024-2026 guide profile
pages; 2022 and 2023 cheatsheets show only tier rank with no per-player
continuous score.
"""
import json
import re
from pathlib import Path
import pandas as pd


CANONICAL_TIERS = ["Elite", "Starter", "Flex", "Depth", "Dart Throw"]


# Trailing decimal in source_quote = ZAP score for 2024-2026.
# E.g. "TRAVIS HUNTER • WR   97.1" → 97.1
_ZAP_SCORE_PATTERN = re.compile(r"(\d+\.\d+)\s*$")


def parse_zap_score(source_quote: str) -> float | None:
    """Extract trailing decimal from source_quote as the ZAP / Z-Prospect score.

    Returns None when the quote has no trailing decimal (2022/2023 format).
    """
    if not source_quote:
        return None
    m = _ZAP_SCORE_PATTERN.search(source_quote.strip())
    return float(m.group(1)) if m else None


def apply_tier_map(rows: list[dict], tier_map: dict) -> list[dict]:
    """Attach canonical_tier to each row based on (year, original_label) lookup.

    Raises KeyError if a row's tier label is not in the map.
    """
    out = []
    for r in rows:
        year_key = str(r["guide_year"])
        year_table = tier_map.get(year_key) or tier_map.get(int(year_key))
        if year_table is None:
            raise KeyError(f"No tier mapping for year {year_key}")
        label = r["original_tier_label"]
        if label not in year_table:
            raise KeyError(f"Unmapped tier label '{label}' for year {year_key}")
        out.append({**r, "canonical_tier": year_table[label]})
    return out


def build_harmonized_table(rows: list[dict], tier_map: dict) -> pd.DataFrame:
    """Apply tier map and return a DataFrame with canonical_tier as ordered
    category and zap_score parsed from source_quote (NA when not present)."""
    mapped = apply_tier_map(rows, tier_map)
    df = pd.DataFrame(mapped)
    df["canonical_tier"] = pd.Categorical(
        df["canonical_tier"], categories=CANONICAL_TIERS, ordered=True
    )
    df["zap_score"] = df["source_quote"].apply(parse_zap_score)
    return df


def load_all_extractions(output_dir: str) -> list[dict]:
    """Load and concatenate all *_players.json files from output_dir."""
    output_path = Path(output_dir)
    rows: list[dict] = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        path = output_path / f"{year}_players.json"
        if path.exists():
            rows.extend(json.loads(path.read_text()))
    return rows


def main():
    output_dir = Path("analysis/late_round_eval/extraction/output")
    tier_map_path = output_dir / "tier_map.json"
    if not tier_map_path.exists():
        raise FileNotFoundError(
            f"{tier_map_path} not found. Run harmonizer subagent first (Task 5 Step 4)."
        )
    tier_map = json.loads(tier_map_path.read_text())
    # Strip rationale key if present
    tier_map = {k: v for k, v in tier_map.items() if k != "rationale"}

    rows = load_all_extractions(str(output_dir))
    df = build_harmonized_table(rows, tier_map)
    out_path = output_dir / "harmonized.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(df.groupby(["guide_year", "canonical_tier"], observed=True).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
