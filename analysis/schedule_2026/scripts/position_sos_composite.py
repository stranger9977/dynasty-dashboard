"""Composite-adjusted Position SoS for 2026.

Upgrades the FPA-only position SoS by blending in the team-level defensive
quality signals (cap spend, ESPN FPI, Vegas win total). Position-specific FPA
still does the position-scheme heavy-lifting; the team-level signals add a
forward-looking adjustment so we're not purely backward-looking on 2023-25 FPA.

Per-defense per-position composite (0-100):
  50% position-FPA percentile  (low FPA allowed = high pct = good D)
  20% cap spend on defense pct (high cap = good D)
  20% FPI defensive efficiency pct (high FPI = good D)
  10% Vegas win total pct          (high WT = good team = good D proxy)

Per-offense per-position SoS = mean opponent composite across 17 games,
percentile-normalized within the league (higher = tougher schedule).
"""
from __future__ import annotations
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')
from _shared import nflverse, output, teams  # noqa: E402

ROOT = Path("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")
SLUG = "position_sos_composite"

WEIGHTS = {"fpa": 0.50, "cap": 0.20, "fpi": 0.20, "wt": 0.10}


def pct(series: pd.Series, *, low_is_good: bool) -> pd.Series:
    return series.rank(ascending=not low_is_good, pct=True) * 100


def main() -> None:
    pos = pd.read_parquet(ROOT / "output/position_sos/data.parquet")
    qual = pd.read_parquet(ROOT / "output/defensive_quality/data.parquet")

    # We need per-defense per-position FPA-allowed. The existing position_sos data
    # has the OPPONENT'S average FPA from the offense's perspective — i.e., for
    # offense team T, rb_opp_fpa = mean(rb_fpa_allowed across T's 17 opponents).
    # To get per-defense FPA, we have to recompute from the raw FPA frame.
    sched = nflverse.load_schedule_2026()
    home_long = sched[["week", "home_team", "away_team"]].rename(
        columns={"home_team": "team", "away_team": "opp"})
    away_long = sched[["week", "home_team", "away_team"]].rename(
        columns={"away_team": "team", "home_team": "opp"})
    long = pd.concat([home_long, away_long], ignore_index=True)

    # Back-derive defense FPA from offense table by inverting the avg.
    # Easier path: read defensive_quality which already has overall_fpa_allowed,
    # then re-derive per-position from position_sos's offense-avg-of-opps.
    # Cleanest: re-run a focused PBP aggregation for per-position FPA.
    per_def_pos = _per_defense_position_fpa()

    # Build per-defense per-position composite
    qual_team = qual.set_index("team")[["cap_pct", "fpi_pct", "wt_pct"]]
    rows = []
    for pos_label in ["RB", "WR", "TE"]:
        sub = per_def_pos[per_def_pos["position"] == pos_label].copy()
        sub["fpa_pct"] = pct(sub["fpa_per_game"], low_is_good=True)
        merged = sub.merge(qual_team, left_on="defteam", right_index=True, how="left")
        merged["def_pos_quality"] = (
            WEIGHTS["fpa"] * merged["fpa_pct"]
            + WEIGHTS["cap"] * merged["cap_pct"]
            + WEIGHTS["fpi"] * merged["fpi_pct"]
            + WEIGHTS["wt"]  * merged["wt_pct"]
        )
        merged["position"] = pos_label
        rows.append(merged[["defteam", "position", "fpa_per_game", "fpa_pct",
                            "cap_pct", "fpi_pct", "wt_pct", "def_pos_quality"]])
    per_def_pos_q = pd.concat(rows, ignore_index=True)

    # Per-offense per-position SoS = avg opponent def_pos_quality
    pivot = per_def_pos_q.pivot(index="defteam", columns="position", values="def_pos_quality")
    rows = []
    for team in teams.ALL_TEAMS:
        opps = long[long["team"] == team]["opp"].tolist()
        row = {"team": team}
        for p_low, p in [("rb", "RB"), ("wr", "WR"), ("te", "TE")]:
            avg_q = pivot.loc[opps, p].mean()
            row[f"{p_low}_avg_def_quality"] = round(avg_q, 1)
        rows.append(row)
    sos = pd.DataFrame(rows)

    # Convert to SoS percentile (higher = tougher schedule)
    for p_low in ["rb", "wr", "te"]:
        sos[f"{p_low}_sos_score"] = (sos[f"{p_low}_avg_def_quality"]
                                     .rank(ascending=True, pct=True) * 100).round(1)

    output.write_data(SLUG, sos)

    print("Top tough RB schedules:")
    print(sos.sort_values("rb_sos_score", ascending=False)
          .head(5)[["team", "rb_sos_score", "rb_avg_def_quality"]].to_string(index=False))
    print("Top easy RB schedules:")
    print(sos.sort_values("rb_sos_score")
          .head(5)[["team", "rb_sos_score", "rb_avg_def_quality"]].to_string(index=False))


def _per_defense_position_fpa() -> pd.DataFrame:
    """Per-defense per-position FPA/game, recency-weighted 50/30/20."""
    pbp = nflverse.load_pbp([2023, 2024, 2025])
    pbp = pbp[pbp["season_type"] == "REG"]

    rosters = pd.concat([
        nflverse.load_rosters(2024)[["gsis_id", "position"]],
        nflverse.load_rosters(2025)[["gsis_id", "position"]],
    ], ignore_index=True).drop_duplicates("gsis_id")
    pos_map = dict(zip(rosters["gsis_id"], rosters["position"]))

    # Rush attribution
    rush = pbp[pbp["rusher_player_id"].notna() & (pbp["play_type"] == "run")].copy()
    rush["pts"] = (rush["rushing_yards"].fillna(0) * 0.1
                   + rush["rush_touchdown"].fillna(0) * 6
                   - rush["fumble_lost"].fillna(0) * 2)
    rush["pid"] = rush["rusher_player_id"]

    rec = pbp[pbp["receiver_player_id"].notna()
              & (pbp["play_type"] == "pass")
              & (pbp["complete_pass"].fillna(0) == 1)].copy()
    rec["pts"] = (1 + rec["receiving_yards"].fillna(0) * 0.1
                  + rec["pass_touchdown"].fillna(0) * 6
                  - rec["fumble_lost"].fillna(0) * 2)
    rec["pid"] = rec["receiver_player_id"]

    cols = ["season", "week", "game_id", "defteam", "pid", "pts"]
    all_pts = pd.concat([rush[cols], rec[cols]], ignore_index=True)
    all_pts["position"] = all_pts["pid"].map(pos_map)
    all_pts = all_pts[all_pts["position"].isin(["RB", "WR", "TE"])]

    # Per-game per-defense per-position
    per_game = (all_pts.groupby(["season", "game_id", "defteam", "position"])["pts"]
                .sum().reset_index())
    per_season = (per_game.groupby(["season", "defteam", "position"])
                  .agg(fpa_total=("pts", "sum"), n_games=("game_id", "nunique"))
                  .reset_index())
    per_season["fpa_per_game"] = per_season["fpa_total"] / per_season["n_games"]

    weights = {2025: 0.5, 2024: 0.3, 2023: 0.2}
    per_season["w"] = per_season["season"].map(weights)
    sum_w = per_season.groupby(["defteam", "position"])["w"].transform("sum")
    per_season["wn"] = per_season["w"] / sum_w
    per_season["weighted"] = per_season["fpa_per_game"] * per_season["wn"]
    out = (per_season.groupby(["defteam", "position"])["weighted"].sum().reset_index()
           .rename(columns={"weighted": "fpa_per_game"}))
    return out


if __name__ == "__main__":
    main()
