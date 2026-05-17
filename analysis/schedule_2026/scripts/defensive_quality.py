"""Composite defensive quality per NFL team for 2026.

Inputs (all per-team):
  1. Historical FPA — already computed in position_sos/data.parquet (RB+WR+TE allowed,
     recency-weighted 2023/2024/2025 = 0.2/0.3/0.5). Inverted so lower-allowed = better.
  2. Cap spend on defense — Over the Cap 2026 positional spending (USD).
  3. ESPN FPI defensive efficiency — current model rating (higher = better defense).
  4. Vegas win total — overall team strength proxy.

Each signal percentile-ranked (0-100, 100 = best defense). Composite weights:
  FPA 35 · FPI 25 · cap 25 · win_total 15
"""
from __future__ import annotations
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')
from _shared import nflverse, output, teams  # noqa: E402

ROOT = Path("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")
SLUG = "defensive_quality"

# Source 2: Over the Cap 2026 defensive spending (USD)
CAP_SPEND = {
    "NYJ": 71_946_695, "GB": 71_357_304, "CLE": 73_630_463, "BUF": 73_960_487,
    "IND": 77_287_840, "HOU": 70_097_140, "SEA": 69_801_981, "KC":  62_640_728,
    "PIT": 62_116_170, "CIN": 69_081_790, "BAL": 55_951_648, "NE":  48_396_813,
    "LAC": 40_964_620, "ATL": 42_905_867, "DET": 43_846_123, "SF":  53_401_979,
    "JAX": 33_683_922, "TEN": 41_393_199, "NO":  53_405_091, "MIN": 59_584_398,
    "CAR": 38_946_216, "ARI": 47_027_173, "DAL": 48_533_831, "LA":  60_152_973,
    "TB":  58_165_933, "PHI": 38_463_480, "WAS": 45_578_999, "MIA": 55_177_858,
    "LV":  27_336_916, "NYG": 46_466_755, "CHI": 61_432_297,
    "DEN": 53_000_000,  # OTC page 404'd — placeholder near league median
}

# Source 3: ESPN FPI defensive efficiency (higher = better defense)
FPI_DEF = {
    "SEA": 4.6, "LA":  1.2, "DET":  0.1, "GB":  -0.4, "HOU":  4.1, "PHI":  3.3,
    "BUF": -0.5, "BAL": 0.6, "JAX":  1.3, "NE":   1.0, "SF":  -1.9, "LAC":  2.6,
    "CIN": -2.9, "CHI": -0.7, "DEN":  2.6, "NYG": -2.2, "PIT":  0.1, "DAL": -4.3,
    "TB":  -0.8, "KC":   1.7, "IND": -0.8, "WAS": -2.3, "NO":  -2.9, "ATL":  0.3,
    "CAR": -0.8, "ARI": -1.2, "MIN":  3.7, "LV":  -0.2, "TEN": -2.8, "NYJ": -3.9,
    "MIA": -2.5, "CLE":  3.0,
}


def main() -> None:
    # FPA per team (overall = average of RB/WR/TE FPA allowed)
    pos = pd.read_parquet(ROOT / "output/position_sos/data.parquet")
    # FPA columns from position_sos: rb_opp_fpa, wr_opp_fpa, te_opp_fpa — but those are
    # for the OFFENSE'S perspective (avg of opponents' FPA). We need the defense's own
    # FPA. The data.parquet's per-team FPA is what the team's DEFENSE allows.
    # In our existing schema, the team column = offense; rb_opp_fpa = avg of opponents'
    # rb_fpa_allowed. We need to invert — load the raw per-defense FPA.
    pbp_fpa = _compute_per_defense_fpa()

    # Build the composite table
    league_teams = teams.ALL_TEAMS
    df = pd.DataFrame({"team": league_teams})
    df["cap_spend"] = df["team"].map(CAP_SPEND)
    df["fpi_def"]   = df["team"].map(FPI_DEF)
    df = df.merge(pbp_fpa, on="team", how="left")

    # Win totals
    wt = nflverse.load_win_totals_2026()[["team", "win_total"]]
    df = df.merge(wt, on="team", how="left")

    # Composite (defense-positive):
    #   - FPA: low values are good → ascending=True gives higher pct to low-FPA defenses
    #   - cap_spend: high values = more investment = good → ascending=False
    #   - FPI: high = good → ascending=False
    #   - win_total: high = good overall team → ascending=False
    def pct(series, *, low_is_good):
        # low_is_good=True  → small values are good → give them HIGH percentile
        # low_is_good=False → large values are good → give them HIGH percentile
        return series.rank(ascending=not low_is_good, pct=True) * 100

    df["fpa_pct"] = pct(df["overall_fpa_allowed"], low_is_good=True)
    df["cap_pct"] = pct(df["cap_spend"],            low_is_good=False)
    df["fpi_pct"] = pct(df["fpi_def"],              low_is_good=False)
    df["wt_pct"]  = pct(df["win_total"],            low_is_good=False)

    df["def_quality"] = (
        0.35 * df["fpa_pct"]
        + 0.25 * df["fpi_pct"]
        + 0.25 * df["cap_pct"]
        + 0.15 * df["wt_pct"]
    ).round(1)
    df["def_rank"] = df["def_quality"].rank(ascending=False, method="min").astype(int)
    df = df.sort_values("def_quality", ascending=False).reset_index(drop=True)

    output.write_data(SLUG, df)

    print(df[["def_rank", "team", "def_quality",
              "fpa_pct", "cap_pct", "fpi_pct", "wt_pct"]].to_string(index=False))


def _compute_per_defense_fpa() -> pd.DataFrame:
    """Compute each defense's avg FPA allowed (averaged across RB/WR/TE) from PBP."""
    pbp = nflverse.load_pbp([2023, 2024, 2025])
    pbp = pbp[pbp["season_type"] == "REG"].copy()

    # PPR fantasy points per player-play
    rush_pts = (pbp["rushing_yards"].fillna(0) * 0.1
                + pbp["rush_touchdown"].fillna(0) * 6
                - pbp["fumble_lost"].fillna(0) * 2)
    rec_pts  = (pbp["complete_pass"].fillna(0) * 1
                + pbp["receiving_yards"].fillna(0) * 0.1
                + pbp["pass_touchdown"].fillna(0) * 6
                - pbp["fumble_lost"].fillna(0) * 2)

    rusher = pbp[["season", "week", "defteam", "rusher_player_id"]].copy()
    rusher["pts"] = rush_pts
    rusher = rusher.rename(columns={"rusher_player_id": "player_id"})
    rusher = rusher.dropna(subset=["defteam", "player_id"])

    receiver = pbp[["season", "week", "defteam", "receiver_player_id"]].copy()
    receiver["pts"] = rec_pts
    receiver = receiver.rename(columns={"receiver_player_id": "player_id"})
    receiver = receiver.dropna(subset=["defteam", "player_id"])

    # We don't filter by position here — just sum total skill-position FPA allowed.
    # This is a coarse overall-defense metric (intentional simplification for the composite).
    all_pts = pd.concat([rusher, receiver], ignore_index=True)
    per_game = (all_pts.groupby(["season", "week", "defteam", "player_id"])["pts"].sum()
                .reset_index())
    per_def_game = per_game.groupby(["season", "defteam"])["pts"].agg(["sum", "count"]).reset_index()
    per_def_game["games"] = per_def_game["count"] / 25  # ~25 skill-position player-games per team-game; rough denominator
    per_def_game["fpa_per_game"] = per_def_game["sum"] / per_def_game.groupby("season")["sum"].transform("sum") * 1000

    # Recency-weighted average per defense (2023=0.2, 2024=0.3, 2025=0.5)
    pivot = per_def_game.pivot(index="defteam", columns="season", values="fpa_per_game")
    pivot = pivot.rename(columns={2023: "y23", 2024: "y24", 2025: "y25"})
    pivot["overall_fpa_allowed"] = 0.2 * pivot["y23"] + 0.3 * pivot["y24"] + 0.5 * pivot["y25"]
    return pivot.reset_index().rename(columns={"defteam": "team"})[["team", "overall_fpa_allowed"]]


if __name__ == "__main__":
    main()
