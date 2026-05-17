"""Canonical Strength of Schedule from Vegas implied wins.

Each team's win_total from Vegas IS that team's implied wins. A team's SoS is the
sum (or mean) of their 17 opponents' implied wins. Higher = harder schedule.
"""
from __future__ import annotations
import sys
sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams


def build_opponent_long(schedule: pd.DataFrame) -> pd.DataFrame:
    home = schedule.rename(columns={"home_team": "team", "away_team": "opp"})[["week", "team", "opp"]]
    away = schedule.rename(columns={"away_team": "team", "home_team": "opp"})[["week", "team", "opp"]]
    return pd.concat([home, away], ignore_index=True)


def main() -> None:
    slug = "implied_wins_sos"
    schedule = nflverse.load_schedule_2026()
    wt = nflverse.load_win_totals_2026()[["team", "win_total"]].rename(columns={"win_total": "implied_wins"})

    long = build_opponent_long(schedule)
    long = long.merge(wt, left_on="opp", right_on="team", suffixes=("", "_opp")).drop(columns=["team_opp"])

    by_team = (
        long.groupby("team")
        .agg(games=("opp", "size"),
             total_opp_implied_wins=("implied_wins", "sum"),
             avg_opp_implied_wins=("implied_wins", "mean"),
             min_opp_iw=("implied_wins", "min"),
             max_opp_iw=("implied_wins", "max"),
             std_opp_iw=("implied_wins", "std"))
        .reset_index()
    )

    league_avg = wt["implied_wins"].mean()
    by_team["sos_vs_league_avg"] = by_team["avg_opp_implied_wins"] - league_avg
    by_team["sos_rank"] = by_team["total_opp_implied_wins"].rank(ascending=False, method="min").astype(int)
    by_team = by_team.sort_values("total_opp_implied_wins", ascending=False).reset_index(drop=True)

    by_team["division"] = by_team["team"].map(teams.DIVISIONS)

    output.write_data(slug, by_team)

    fig, ax = plt.subplots(figsize=(11, 9))
    sorted_df = by_team.sort_values("total_opp_implied_wins")
    colors = ["#c43d3d" if v > 0 else "#3d8fc4" for v in sorted_df["sos_vs_league_avg"]]
    ax.barh(sorted_df["team"], sorted_df["total_opp_implied_wins"], color=colors, edgecolor="#222")
    ax.axvline(league_avg * 17, color="#888", linestyle="--", linewidth=1, label=f"League avg ({league_avg*17:.1f})")
    ax.set_xlabel("Sum of opponent implied wins (17 games)")
    ax.set_title("2026 Strength of Schedule — Total Opponent Implied Wins (Vegas)", fontsize=13)
    ax.legend(loc="lower right")
    for i, row in enumerate(sorted_df.itertuples()):
        ax.text(row.total_opp_implied_wins + 0.3, i, f"{row.total_opp_implied_wins:.1f}",
                va="center", fontsize=8, color="#333")
    ax.set_xlim(left=sorted_df["total_opp_implied_wins"].min() - 5)
    fig.tight_layout()
    fig.savefig(output.chart_path(slug), dpi=110)
    plt.close(fig)

    hardest = by_team.head(5)
    easiest = by_team.tail(5).iloc[::-1]
    league_total = league_avg * 17

    findings = f"""# Strength of Schedule — Total Opponent Implied Wins

**Methodology.** Each team's Vegas win total *is* their implied wins. A team's
SoS is the sum of their 17 opponents' implied wins. Higher = tougher slate.
League baseline = league-mean implied wins × 17 = **{league_total:.1f}**.

## Hardest schedules

{chr(10).join(f"- **{r.team}** ({r.division}) — {r.total_opp_implied_wins:.1f} total ({r.sos_vs_league_avg:+.2f} vs avg, opps avg {r.avg_opp_implied_wins:.2f} wins)" for r in hardest.itertuples())}

## Easiest schedules

{chr(10).join(f"- **{r.team}** ({r.division}) — {r.total_opp_implied_wins:.1f} total ({r.sos_vs_league_avg:+.2f} vs avg, opps avg {r.avg_opp_implied_wins:.2f} wins)" for r in easiest.itertuples())}

## Notes

- Total spread: {by_team['total_opp_implied_wins'].iloc[0] - by_team['total_opp_implied_wins'].iloc[-1]:.1f} wins between hardest and easiest schedule.
- This is the canonical SoS lens — every other schedule analysis in this module
  derives from this same opponent-quality input (see `front_back_sos`,
  `schedule_luck`, `gauntlet`).
- Source: Vegas win totals from Rotowire / DraftKings, dated 2026-05-15 (the day
  after schedule release — lines will move).
"""
    output.write_findings(slug, findings)
    print(by_team[["sos_rank", "team", "division", "total_opp_implied_wins", "avg_opp_implied_wins", "sos_vs_league_avg"]].to_string(index=False))


if __name__ == "__main__":
    main()
