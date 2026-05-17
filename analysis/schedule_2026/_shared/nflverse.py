"""Loaders for nflverse data. Assumes raw files in ../data/raw/ relative to this file's parent."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

# data/raw lives at analysis/schedule_2026/data/raw
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def load_games() -> pd.DataFrame:
    """Full historical schedule incl. 2026 (272 games). Has spreads/totals for past games only."""
    return pd.read_csv(RAW / "games.csv", low_memory=False)


def load_schedule_2026() -> pd.DataFrame:
    g = load_games()
    return g[g["season"] == 2026].copy().reset_index(drop=True)


def load_pbp(seasons: list[int] | None = None) -> pd.DataFrame:
    """Play-by-play across requested seasons (default: all available 2020-2025)."""
    seasons = seasons or [2020, 2021, 2022, 2023, 2024, 2025]
    frames = []
    for s in seasons:
        p = RAW / f"pbp_{s}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        raise FileNotFoundError(f"No PBP parquet files for seasons {seasons}")
    return pd.concat(frames, ignore_index=True)


def load_rosters(season: int = 2025) -> pd.DataFrame:
    return pd.read_csv(RAW / f"rosters_{season}.csv", low_memory=False)


def load_win_totals_2026() -> pd.DataFrame | None:
    """2026 Vegas win totals (scraped). Returns None if not yet generated."""
    p = RAW / "win_totals_2026.csv"
    if not p.exists():
        return None
    return pd.read_csv(p)
