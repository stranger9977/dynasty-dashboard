"""QB schedule strength — opponent-pass-defense quality per team.

QB FPA allowed per defense: standard scoring (pass_yds*0.04 + pass_td*4 - int*2
+ rush_yds*0.1 + rush_td*6 - fumble_lost*2). Recency-weighted 50/30/20 across
2023-2025. Then for each 2026 offense, average the opponents' QB-FPA-allowed
across all 17 games to get the season schedule strength.
"""
from __future__ import annotations
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')
from _shared import nflverse, output  # noqa: E402

ROOT = Path("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")
TEAM_FIX = {"GBP": "GB", "KCC": "KC", "LVR": "LV", "NOS": "NO",
            "SFO": "SF", "TBB": "TB", "LAR": "LA"}


def qb_fpa_allowed_per_defense() -> pd.DataFrame:
    pbp = nflverse.load_pbp([2023, 2024, 2025])
    pbp = pbp[pbp["season_type"] == "REG"].copy()

    # QB-scoring: pass yds * 0.04, pass TD * 4, INT -2, rush yds * 0.1, rush TD * 6
    pass_pts = (pbp["passing_yards"].fillna(0) * 0.04
                + pbp["pass_touchdown"].fillna(0) * 4
                - pbp["interception"].fillna(0) * 2)
    rush_pts = (pbp["rushing_yards"].fillna(0) * 0.1
                + pbp["rush_touchdown"].fillna(0) * 6)
    fumble = pbp["fumble_lost"].fillna(0) * 2

    qb_pbp = pbp[["season", "week", "defteam",
                  "passer_player_id", "rusher_player_id"]].copy()
    qb_pbp["pass_pts"]  = pass_pts
    qb_pbp["rush_pts"]  = rush_pts
    qb_pbp["fumble"]    = fumble
    qb_pbp = qb_pbp.dropna(subset=["defteam"])

    # Roster lookup to filter rushing to QBs only (RB rushes shouldn't count as QB FPA)
    rosters = pd.concat([
        nflverse.load_rosters(2024)[["gsis_id", "position"]],
        nflverse.load_rosters(2025)[["gsis_id", "position"]],
    ], ignore_index=True).drop_duplicates("gsis_id")
    qb_ids = set(rosters[rosters["position"] == "QB"]["gsis_id"])

    qb_pbp.loc[~qb_pbp["rusher_player_id"].isin(qb_ids), "rush_pts"] = 0
    # passer is always a QB-ish role; keep all passing pts
    qb_pbp["total"] = qb_pbp["pass_pts"] + qb_pbp["rush_pts"] - qb_pbp["fumble"]

    per_def_game = qb_pbp.groupby(["season", "defteam", "week"])["total"].sum().reset_index()
    per_def_season = per_def_game.groupby(["season", "defteam"])["total"].mean().reset_index()
    per_def_season = per_def_season.rename(columns={"total": "qb_fpa_per_game"})

    pivot = per_def_season.pivot(index="defteam", columns="season", values="qb_fpa_per_game")
    pivot.columns = [f"y{c}" for c in pivot.columns]
    pivot["qb_fpa_allowed"] = 0.2 * pivot["y2023"] + 0.3 * pivot["y2024"] + 0.5 * pivot["y2025"]
    return pivot.reset_index().rename(columns={"defteam": "team"})[["team", "qb_fpa_allowed"]]


def top_qb_per_team() -> pd.DataFrame:
    m = pd.read_parquet("/Users/nick/projects/dynasty-dashboard/data/merged.parquet")
    qbs = m[(m["position"] == "QB") & (m["team"] != "FA")].copy()
    qbs["team"] = qbs["team"].replace(TEAM_FIX)
    return (qbs.sort_values("blended_value", ascending=False)
            .drop_duplicates("team")[["name", "team", "blended_value", "age"]]
            .rename(columns={"name": "top_player"}))


def main() -> None:
    qb_def = qb_fpa_allowed_per_defense()
    sched = nflverse.load_schedule_2026()

    home = sched.rename(columns={"home_team": "team", "away_team": "opp"})[["week", "team", "opp"]]
    away = sched.rename(columns={"away_team": "team", "home_team": "opp"})[["week", "team", "opp"]]
    long = pd.concat([home, away], ignore_index=True)
    long = long.merge(qb_def, left_on="opp", right_on="team", suffixes=("", "_def")).drop(columns=["team_def"])

    per_team = (long.groupby("team")["qb_fpa_allowed"].mean()
                .reset_index().rename(columns={"qb_fpa_allowed": "opp_fpa"}))
    per_team["sos_score"] = (1 - per_team["opp_fpa"].rank(pct=True)) * 100  # invert: low FPA allowed = tough = high score
    per_team["sos_score"] = per_team["sos_score"].round(1)

    top = top_qb_per_team()
    df = per_team.merge(top, on="team", how="left")
    df = df.sort_values("sos_score", ascending=False).reset_index(drop=True)

    out_dir = ROOT / "output" / "position_schedules"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "qb_schedule.parquet", index=False)

    print("[QB] top-5 toughest schedules:")
    print(df.head(5)[["team", "top_player", "sos_score", "opp_fpa", "blended_value"]].to_string(index=False))
    print("[QB] top-5 easiest schedules:")
    print(df.tail(5).iloc[::-1][["team", "top_player", "sos_score", "opp_fpa", "blended_value"]].to_string(index=False))


if __name__ == "__main__":
    main()
