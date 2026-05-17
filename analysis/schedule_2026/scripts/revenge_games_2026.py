"""Regenerate revenge_games using ACTUAL 2026 rosters (now available in nflverse).

Earlier version used 2025 rosters as a 2026 proxy — that's now stale for any
player who moved in 2026 free agency (e.g., Kenneth Gainwell off PIT).
"""
from __future__ import annotations
from pathlib import Path
import sys
import subprocess

import pandas as pd

sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')
from _shared import nflverse, output  # noqa: E402

ROOT = Path("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")
SLUG = "revenge_games"


def _load_2026_rosters() -> pd.DataFrame:
    """Pull 2026 rosters via R/nflreadr (Python doesn't have a direct nflverse loader)."""
    cache = ROOT / "data/raw/rosters_2026.csv"
    if not cache.exists():
        subprocess.run([
            "Rscript", "-e",
            f'r <- nflreadr::load_rosters(2026); '
            f'write.csv(r, "{cache}", row.names=FALSE)'
        ], check=True)
    return pd.read_csv(cache, low_memory=False)


def _cross_with_schedule(moved: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    home_long = sched[["week", "gameday", "home_team", "away_team"]].rename(
        columns={"home_team": "team", "away_team": "opp"}).assign(home_or_away="home")
    away_long = sched[["week", "gameday", "home_team", "away_team"]].rename(
        columns={"away_team": "team", "home_team": "opp"}).assign(home_or_away="away")
    long = pd.concat([home_long, away_long], ignore_index=True)

    games = moved.merge(long, left_on=["current_team", "former_team"],
                        right_on=["team", "opp"]).drop(columns=["team", "opp"])
    return (games.rename(columns={"full_name": "player_name",
                                  "week": "revenge_week",
                                  "gameday": "game_date"})
            .sort_values(["revenge_week", "player_name"])
            .reset_index(drop=True))


def main() -> None:
    r24 = nflverse.load_rosters(2024)
    r25 = nflverse.load_rosters(2025)
    r26 = _load_2026_rosters()

    skill = {"QB", "RB", "WR", "TE"}
    for df in (r24, r25, r26):
        df["full_name"] = df["full_name"].astype(str)

    active = (r26[(r26["position"].isin(skill))
                  & (r26["status"].isin(["ACT", "RES", "PUP"]))]
              [["gsis_id", "full_name", "position", "team", "years_exp",
                "rookie_year", "draft_club"]]
              .rename(columns={"team": "current_team"})
              .drop_duplicates("gsis_id"))

    DRAFT_FIX = {"OAK": "LV", "STL": "LA", "SD": "LAC"}
    active["draft_club"] = active["draft_club"].replace(DRAFT_FIX)

    sched = nflverse.load_schedule_2026()

    # ── Flavor A: vs MOST RECENT FORMER TEAM ─────────────────────────────
    prior = pd.concat([
        r24[["gsis_id", "team"]].assign(season=2024),
        r25[["gsis_id", "team"]].assign(season=2025),
    ], ignore_index=True).dropna(subset=["gsis_id"])

    joined = active.merge(prior, on="gsis_id")
    recent_moved = joined[joined["current_team"] != joined["team"]].copy()
    recent_moved = (recent_moved[["gsis_id", "full_name", "position", "current_team",
                                  "team", "years_exp", "season"]]
                    .rename(columns={"team": "former_team",
                                     "season": "left_after_season"})
                    .drop_duplicates(["gsis_id", "former_team"]))

    games_recent = _cross_with_schedule(recent_moved, sched)
    games_recent = games_recent[["player_name", "position", "current_team",
                                 "former_team", "revenge_week", "game_date",
                                 "home_or_away", "years_exp", "left_after_season"]]
    output.write_data(SLUG, games_recent)  # primary file: recent former
    print(f"[recent-former] {len(games_recent)} games for {games_recent['player_name'].nunique()} players.")

    # ── Flavor B: vs DRAFTED TEAM ────────────────────────────────────────
    drafted = active[active["draft_club"].notna() &
                     (active["current_team"] != active["draft_club"])].copy()
    drafted = (drafted[["gsis_id", "full_name", "position", "current_team",
                        "draft_club", "years_exp", "rookie_year"]]
               .rename(columns={"draft_club": "former_team"}))

    games_drafted = _cross_with_schedule(drafted, sched)
    games_drafted = games_drafted[["player_name", "position", "current_team",
                                   "former_team", "revenge_week", "game_date",
                                   "home_or_away", "years_exp", "rookie_year"]]
    out_path = output.artifact_dir(SLUG) / "data_drafted.parquet"
    games_drafted.to_parquet(out_path, index=False)
    print(f"[drafted-team] {len(games_drafted)} games for {games_drafted['player_name'].nunique()} players.")


if __name__ == "__main__":
    main()
