"""Does SoS actually matter? Historical retrospective 2017-2024.

For each season-team:
  - Preseason "strength" = average spread (negative = favored) across their first
    3 games' lines. This is Vegas's early-season power read, before too many actual
    results have leaked in.
  - Schedule SoS = average of opponents' preseason strength across all 17 games.
  - Actual outcome = final win count.

We then test: does SoS predict wins above-and-beyond own team strength?
"""
from __future__ import annotations
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')
from _shared import output  # noqa: E402

ROOT = Path("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")
SLUG = "sos_matters"


def main() -> None:
    g = pd.read_csv(ROOT / "data/raw/games.csv", low_memory=False)
    g = g[(g["game_type"] == "REG") & g["season"].between(2017, 2024)].copy()

    # Per-team-game spread from the team's perspective (negative = favored).
    home = g[["season", "week", "home_team", "away_team", "spread_line", "result"]].rename(
        columns={"home_team": "team", "away_team": "opp"})
    home["team_spread"] = home["spread_line"]   # home perspective
    home["team_win"] = (home["result"] > 0).astype(int)
    home["team_score_diff"] = home["result"]

    away = g[["season", "week", "home_team", "away_team", "spread_line", "result"]].rename(
        columns={"away_team": "team", "home_team": "opp"})
    away["team_spread"] = -away["spread_line"]  # flip for away
    away["team_win"] = (away["result"] < 0).astype(int)
    away["team_score_diff"] = -away["result"]

    tg = pd.concat([home, away], ignore_index=True)
    tg = tg.dropna(subset=["team_spread", "team_win"])

    # Preseason strength per team-season: avg team_spread across their first 3 games.
    # More negative spread = stronger team. Convert to a positive-is-good "strength" by negating.
    pre = (tg[tg["week"] <= 3]
           .groupby(["season", "team"])["team_spread"].mean()
           .reset_index()
           .rename(columns={"team_spread": "early_spread"}))
    pre["preseason_strength"] = -pre["early_spread"]

    # Per-season SoS: each team's average opponent preseason_strength
    opp_strength = pre[["season", "team", "preseason_strength"]].rename(
        columns={"team": "opp", "preseason_strength": "opp_strength"})
    tg2 = tg.merge(opp_strength, on=["season", "opp"])
    sos = (tg2.groupby(["season", "team"])["opp_strength"].mean()
           .reset_index().rename(columns={"opp_strength": "sos"}))

    # Actual wins per team-season
    wins = (tg.groupby(["season", "team"])["team_win"].sum()
            .reset_index().rename(columns={"team_win": "actual_wins"}))

    # Combine
    df = pre[["season", "team", "preseason_strength"]].merge(sos, on=["season", "team"]).merge(wins, on=["season", "team"])
    df = df.dropna()

    # Compute SoS percentile within each season
    df["sos_pct"] = df.groupby("season")["sos"].rank(pct=True) * 100

    output.write_data(SLUG, df)

    # Summary stats
    # 1. Raw correlation: SoS vs actual_wins
    corr_raw = df[["sos", "actual_wins"]].corr().iloc[0, 1]

    # 2. Partial: regress wins on own_strength + sos; report SoS coefficient
    from numpy.linalg import lstsq
    X = np.column_stack([np.ones(len(df)), df["preseason_strength"], df["sos"]])
    y = df["actual_wins"].to_numpy()
    coef, *_ = lstsq(X, y, rcond=None)
    intercept, b_strength, b_sos = coef

    # Residual after own strength
    pred_from_strength = intercept + b_strength * df["preseason_strength"]
    df["wins_minus_strength_only"] = df["actual_wins"] - pred_from_strength

    # 3. Decile / tail analysis: hardest 10% vs easiest 10%
    df["sos_decile"] = pd.qcut(df["sos_pct"], 10, labels=False) + 1
    decile_summary = df.groupby("sos_decile").agg(
        n=("team", "count"),
        avg_sos=("sos", "mean"),
        avg_wins=("actual_wins", "mean"),
        avg_strength=("preseason_strength", "mean"),
        avg_residual=("wins_minus_strength_only", "mean"),
    ).reset_index()

    print("== Headline numbers ==")
    print(f"Raw correlation (SoS vs actual wins): r = {corr_raw:+.3f}")
    print(f"Regression: wins = {intercept:.2f} + {b_strength:+.3f}*strength + {b_sos:+.3f}*SoS")
    print(f"  → 1-pt SoS swing = {b_sos:+.2f} wins (controlling for own strength)")
    print()
    print("== Decile summary (1 = easiest schedule, 10 = hardest) ==")
    print(decile_summary.to_string(index=False))
    print()
    print(f"Hardest decile actual wins: {decile_summary.iloc[-1].avg_wins:.2f}")
    print(f"Easiest decile actual wins: {decile_summary.iloc[0].avg_wins:.2f}")
    print(f"Difference: {decile_summary.iloc[-1].avg_wins - decile_summary.iloc[0].avg_wins:+.2f} wins")
    print()
    print(f"Residual (wins above strength-only prediction):")
    print(f"  Hardest decile: {decile_summary.iloc[-1].avg_residual:+.2f}")
    print(f"  Easiest decile: {decile_summary.iloc[0].avg_residual:+.2f}")


if __name__ == "__main__":
    main()
