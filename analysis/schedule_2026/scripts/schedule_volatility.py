"""Schedule volatility — std/spread of opponent implied wins per team.

High volatility = boom/bust schedule (mix of strong and weak opponents).
Low volatility = steady-quality schedule (most opponents cluster near league avg).

This is a schedule SHAPE signal that does NOT reduce to NFL scheduling rules —
it varies materially across teams even though opponent sets are partly determined
by the league formula.
"""
from __future__ import annotations
import sys
sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams


def main() -> None:
    slug = "schedule_volatility"
    schedule = nflverse.load_schedule_2026()
    wt = nflverse.load_win_totals_2026()[["team", "win_total"]]

    home = schedule.rename(columns={"home_team": "team", "away_team": "opp"})[["week", "team", "opp"]]
    away = schedule.rename(columns={"away_team": "team", "home_team": "opp"})[["week", "team", "opp"]]
    long = pd.concat([home, away], ignore_index=True)
    long = long.merge(wt, left_on="opp", right_on="team", suffixes=("", "_o")).drop(columns=["team_o"])
    long = long.rename(columns={"win_total": "opp_wt"})

    summary = (
        long.groupby("team")
        .agg(opp_wt_mean=("opp_wt", "mean"),
             opp_wt_std=("opp_wt", "std"),
             opp_wt_min=("opp_wt", "min"),
             opp_wt_max=("opp_wt", "max"))
        .reset_index()
    )
    summary["spread"] = summary["opp_wt_max"] - summary["opp_wt_min"]
    summary["division"] = summary["team"].map(teams.DIVISIONS)
    summary = summary.sort_values("opp_wt_std", ascending=True).reset_index(drop=True)

    output.write_data(slug, summary)

    fig, ax = plt.subplots(figsize=(11, 9))
    norm = (summary["opp_wt_std"] - summary["opp_wt_std"].min()) / (summary["opp_wt_std"].max() - summary["opp_wt_std"].min())
    colors = plt.cm.plasma(norm)
    ax.barh(range(len(summary)), summary["opp_wt_std"], color=colors, edgecolor="#222")
    league_avg_std = summary["opp_wt_std"].mean()
    ax.axvline(league_avg_std, color="#888", linestyle="--", linewidth=1, label=f"League avg ({league_avg_std:.2f})")

    # Add spread (min-max) as a faded gray reference on the right axis
    for i, r in enumerate(summary.itertuples()):
        ax.text(r.opp_wt_std + 0.02, i, f"σ={r.opp_wt_std:.2f}  spread={r.spread:.1f}  (opps {r.opp_wt_min:.1f}-{r.opp_wt_max:.1f})",
                va="center", fontsize=8, color="#444")

    ax.set_yticks(range(len(summary)))
    ax.set_yticklabels(summary["team"], fontsize=9)
    ax.set_xlabel("Std of opponent implied wins across 17 games  (higher = more boom/bust)")
    ax.set_title("2026 Schedule Volatility — variance of opponent quality per team", fontsize=13)
    ax.set_xlim(right=summary["opp_wt_std"].max() * 1.65)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(output.chart_path(slug), dpi=110)
    plt.close(fig)

    high = summary.tail(5).iloc[::-1]
    low = summary.head(5)

    findings = f"""# Schedule volatility — variance of opponent quality

**Methodology.** Compute the standard deviation of opponent Vegas win totals
across each team's 17 games. Higher σ = a "boom/bust" schedule with a wide mix
of cupcakes and contenders. Lower σ = a "steady" slate where every opponent
clusters near average quality.

**Why this beats Jaccard on shared opponents:** Volatility varies meaningfully
across teams even though the NFL formula locks much of the opponent set.

## Most volatile schedules (boom/bust)

{chr(10).join(f"- **{r.team}** — σ={r.opp_wt_std:.2f}, range {r.opp_wt_min:.1f}-{r.opp_wt_max:.1f} ({r.spread:.1f} spread)" for r in high.itertuples())}

## Most steady schedules

{chr(10).join(f"- **{r.team}** — σ={r.opp_wt_std:.2f}, range {r.opp_wt_min:.1f}-{r.opp_wt_max:.1f}" for r in low.itertuples())}

## What it means

- Volatile schedules → wider distribution of possible final records. A team with
  σ=3.0 could easily go 10-7 or 6-11 depending on which version shows up each week.
- Steady schedules → outcomes pile up near the team's projection. Easier to bet
  win totals on; harder to "get lucky" with hot streaks.
- For futures markets, volatile-schedule teams are more attractive on the over
  (because the upside is concentrated in beatable opponents) but require more
  variance tolerance.
"""
    output.write_findings(slug, findings)
    print(summary[["team", "division", "opp_wt_mean", "opp_wt_std", "spread"]].to_string(index=False))


if __name__ == "__main__":
    main()
