# ingestion/seed.py
"""Populate gitignored data/ from committed data/seed/ on a fresh clone (cloud)."""
import shutil

from config import DATA_DIR, SEED_DIR

SEED_FILES = [
    "fantasycalc.parquet", "ktc.parquet", "merged.parquet", "nfl_draft.parquet",
    "lateround_rankings.csv", "adp_rankings.csv",
]


def ensure_data_from_seed() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for fname in SEED_FILES:
        dst = DATA_DIR / fname
        src = SEED_DIR / fname
        if not dst.exists() and src.exists():
            shutil.copy(src, dst)
