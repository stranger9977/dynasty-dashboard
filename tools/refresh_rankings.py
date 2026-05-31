"""CLI ranking refresh — pulls fresh FantasyCalc + KeepTradeCut values and
rebuilds merged.parquet. Mirrors the sidebar "Refresh Data" button so you can
refresh from the terminal (e.g. right before a live draft) without the app.

    uv run python tools/refresh_rankings.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, FC_PARQUET, KTC_PARQUET, MERGED_PARQUET  # noqa: E402
from ingestion.fantasycalc import fetch_fantasycalc  # noqa: E402
from ingestion.ktc import fetch_ktc  # noqa: E402
from ingestion.matching import merge_rankings  # noqa: E402


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    print("Fetching FantasyCalc...")
    fc = fetch_fantasycalc()
    fc.to_parquet(FC_PARQUET, index=False)
    print(f"  FantasyCalc: {len(fc)} players  ({fc['is_rookie'].sum()} rookies)")

    print("Fetching KeepTradeCut...")
    kt = fetch_ktc()
    kt.to_parquet(KTC_PARQUET, index=False)
    print(f"  KeepTradeCut: {len(kt)} players  ({int(kt['is_rookie'].sum())} rookies)")

    print("Fetching NFL draft capital...")
    from ingestion.nfl_draft import fetch_nfl_draft
    from config import NFL_DRAFT_PARQUET
    try:
        nd = fetch_nfl_draft()
        nd.to_parquet(NFL_DRAFT_PARQUET, index=False)
        print(f"  NFL draft: {len(nd)} skill picks")
    except Exception as e:
        print(f"  NFL draft fetch failed ({e}) — keeping existing file")

    print("Fetching 2026 projections...")
    from ingestion.projections import fetch_projections
    from config import PROJECTIONS_PARQUET
    try:
        pr = fetch_projections()
        pr.to_parquet(PROJECTIONS_PARQUET, index=False)
        print(f"  Projections: {len(pr)} skill players")
    except Exception as e:
        print(f"  Projections fetch failed ({e}) — keeping existing file")

    print("Matching players...")
    merged = merge_rankings(fc, kt)
    merged.to_parquet(MERGED_PARQUET, index=False)
    both = merged[merged["fc_rank"].notna() & merged["ktc_rank"].notna()]
    fc_only = merged[merged["fc_rank"].notna() & merged["ktc_rank"].isna()]
    ktc_only = merged[merged["fc_rank"].isna() & merged["ktc_rank"].notna()]
    rookies = merged[merged["is_rookie"] == True]  # noqa: E712
    print(f"  Matched (both):   {len(both)}")
    print(f"  FC only (orphan): {len(fc_only)}")
    print(f"  KTC only (orphan):{len(ktc_only)}")
    print(f"  Rookies total:    {len(rookies)}")
    print(f"\nWrote {MERGED_PARQUET}")


if __name__ == "__main__":
    main()
