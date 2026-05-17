"""Bye leverage analysis for the NFL 2026 schedule.

Computes each team's bye week, classifies its fantasy-football quality, counts how
many opponents are coming off a bye (a disadvantage), and computes the season-long
rest differential (sum over 17 games of team_rest - opponent_rest).

Run:
    cd /Users/nick/projects/dynasty-dashboard && \
        uv run python analysis/schedule_2026/scripts/bye_leverage.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "bye_leverage"


def classify_bye(week: int) -> str:
    if 7 <= week <= 11:
        return "FF-optimal"
    if 12 <= week <= 13:
        return "FF-risky"
    if 5 <= week <= 6:
        return "Early"
    if week >= 14:
        return "Late"
    return "Other"


CLASS_COLORS = {
    "FF-optimal": "#2ca02c",   # green
    "FF-risky": "#d62728",     # red
    "Early": "#ff7f0e",        # orange
    "Late": "#1f77b4",         # blue
    "Other": "#7f7f7f",        # grey
}


def compute_team_rows(sched: pd.DataFrame) -> pd.DataFrame:
    """Long-form: one row per team per game, with own_rest, opp_rest, opp_off_bye flag."""
    home = sched.rename(
        columns={
            "home_team": "team",
            "away_team": "opp",
            "home_rest": "own_rest",
            "away_rest": "opp_rest",
        }
    )[["week", "team", "opp", "own_rest", "opp_rest"]]
    away = sched.rename(
        columns={
            "away_team": "team",
            "home_team": "opp",
            "away_rest": "own_rest",
            "home_rest": "opp_rest",
        }
    )[["week", "team", "opp", "own_rest", "opp_rest"]]
    rows = pd.concat([home, away], ignore_index=True)
    rows["opp_off_bye"] = (rows["opp_rest"] == 14).astype(int)
    rows["own_off_bye"] = (rows["own_rest"] == 14).astype(int)
    rows["rest_diff"] = rows["own_rest"] - rows["opp_rest"]
    return rows


def derive_bye_weeks(rows: pd.DataFrame) -> dict[str, int]:
    """A team's bye is the (regular-season) week 1..18 in which they don't play."""
    all_weeks = set(range(1, 19))
    byes: dict[str, int] = {}
    for team, sub in rows.groupby("team"):
        played = set(int(w) for w in sub["week"].unique())
        missing = sorted(all_weeks - played)
        # Take the first missing week (each team has exactly one bye in weeks 1-18).
        byes[team] = missing[0] if missing else -1
    return byes


def build_summary(rows: pd.DataFrame, byes: dict[str, int]) -> pd.DataFrame:
    grouped = rows.groupby("team").agg(
        opps_off_bye=("opp_off_bye", "sum"),
        rest_differential_sum=("rest_diff", "sum"),
        games=("week", "count"),
    ).reset_index()
    grouped["bye_week"] = grouped["team"].map(byes)
    grouped["bye_classification"] = grouped["bye_week"].map(classify_bye)
    grouped = grouped[
        ["team", "bye_week", "bye_classification", "opps_off_bye", "rest_differential_sum", "games"]
    ].sort_values("team").reset_index(drop=True)
    return grouped


def make_chart(df: pd.DataFrame, path) -> None:
    plot_df = df.sort_values("rest_differential_sum", ascending=True).reset_index(drop=True)
    colors = [CLASS_COLORS.get(c, "#7f7f7f") for c in plot_df["bye_classification"]]

    fig, ax = plt.subplots(figsize=(11, 11))
    y = np.arange(len(plot_df))
    bars = ax.barh(y, plot_df["rest_differential_sum"], color=colors, edgecolor="black", linewidth=0.4)
    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{t}  (bye W{int(w)})" for t, w in zip(plot_df["team"], plot_df["bye_week"])],
        fontsize=9,
    )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Season rest differential (team_rest − opp_rest, sum across 17 games)")
    ax.set_title("NFL 2026 Bye Leverage — Rest Differential by Team (colored by bye position)")

    # Annotate each bar with the value and opps-off-bye count.
    xmax = plot_df["rest_differential_sum"].max()
    xmin = plot_df["rest_differential_sum"].min()
    pad = max(abs(xmax), abs(xmin)) * 0.02 + 0.2
    for i, (val, opps) in enumerate(zip(plot_df["rest_differential_sum"], plot_df["opps_off_bye"])):
        offset = pad if val >= 0 else -pad
        ha = "left" if val >= 0 else "right"
        ax.text(val + offset, i, f"{val:+.0f}  (opp-off-bye: {opps})", va="center", ha=ha, fontsize=8)

    # Legend
    from matplotlib.patches import Patch

    legend_elems = [
        Patch(facecolor=CLASS_COLORS["FF-optimal"], edgecolor="black", label="FF-optimal (W7-11)"),
        Patch(facecolor=CLASS_COLORS["FF-risky"], edgecolor="black", label="FF-risky (W12-13)"),
        Patch(facecolor=CLASS_COLORS["Early"], edgecolor="black", label="Early (W5-6)"),
        Patch(facecolor=CLASS_COLORS["Late"], edgecolor="black", label="Late (W14+)"),
    ]
    ax.legend(handles=legend_elems, loc="lower right", framealpha=0.9)
    ax.margins(x=0.18)
    ax.grid(axis="x", linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def build_findings(df: pd.DataFrame) -> str:
    by_rest_desc = df.sort_values("rest_differential_sum", ascending=False).reset_index(drop=True)
    by_rest_asc = df.sort_values("rest_differential_sum", ascending=True).reset_index(drop=True)
    by_opps_desc = df.sort_values("opps_off_bye", ascending=False).reset_index(drop=True)
    by_opps_asc = df.sort_values("opps_off_bye", ascending=True).reset_index(drop=True)

    top_rest = by_rest_desc.iloc[0]
    runner_rest = by_rest_desc.iloc[1]
    worst_rest = by_rest_asc.iloc[0]
    second_worst = by_rest_asc.iloc[1]

    ff_optimal = df[df["bye_classification"] == "FF-optimal"].sort_values("team")
    ff_risky = df[df["bye_classification"] == "FF-risky"].sort_values("team")
    early = df[df["bye_classification"] == "Early"].sort_values("team")
    late = df[df["bye_classification"] == "Late"].sort_values("team")

    most_opps = by_opps_desc.iloc[0]
    most_opps_2 = by_opps_desc.iloc[1]
    fewest_opps = by_opps_asc.iloc[0]

    def fmt_list(sub: pd.DataFrame, max_items: int = 8) -> str:
        items = [f"{r.team} (W{int(r.bye_week)})" for r in sub.itertuples()]
        if len(items) > max_items:
            return ", ".join(items[:max_items]) + f", +{len(items) - max_items} more"
        return ", ".join(items) if items else "none"

    md = f"""# Bye Leverage — 2026 Schedule

- **Best rest situation:** {top_rest.team} leads the league at {int(top_rest.rest_differential_sum):+d} net rest days (bye W{int(top_rest.bye_week)}, {top_rest.bye_classification}), followed by {runner_rest.team} at {int(runner_rest.rest_differential_sum):+d}. These teams systematically face opponents on shorter weeks than themselves.
- **Worst rest situation:** {worst_rest.team} sits at {int(worst_rest.rest_differential_sum):+d} (bye W{int(worst_rest.bye_week)}), with {second_worst.team} ({int(second_worst.rest_differential_sum):+d}) close behind — meaning they routinely hit games more fatigued than the opponent.
- **FF-optimal byes (W7-11):** {fmt_list(ff_optimal)} — these {len(ff_optimal)} teams rest starters during the fantasy regular-season midpoint.
- **FF-risky byes (W12-13):** {fmt_list(ff_risky)} — bye lands during the fantasy stretch run, forcing managers to plug holes right before playoffs.
- **Opponents off bye:** {most_opps.team} draws the most opps-off-bye at {int(most_opps.opps_off_bye)} games (tied/closest: {most_opps_2.team} at {int(most_opps_2.opps_off_bye)}). {fewest_opps.team} faces the fewest at {int(fewest_opps.opps_off_bye)}.
- **Schedule extremes:** Early byes (W5-6): {fmt_list(early)}. Late byes (W14+): {fmt_list(late)}.
"""
    return md


def main() -> None:
    sched = nflverse.load_schedule_2026()
    # Use only regular-season games (272 of them).
    if "game_type" in sched.columns:
        sched = sched[sched["game_type"] == "REG"].copy()
    rows = compute_team_rows(sched)
    byes = derive_bye_weeks(rows)
    summary = build_summary(rows, byes)

    assert len(summary) == 32, f"expected 32 teams, got {len(summary)}"
    assert (summary["games"] == 17).all(), "every team should have 17 games"
    assert summary["bye_week"].between(1, 18).all(), "bye weeks should be 1..18"

    # Persist with the required schema.
    data_df = summary[["team", "bye_week", "bye_classification", "opps_off_bye", "rest_differential_sum"]].copy()
    data_path = output.write_data(SLUG, data_df)
    chart_p = output.chart_path(SLUG)
    make_chart(data_df, chart_p)
    findings_md = build_findings(data_df)
    findings_path = output.write_findings(SLUG, findings_md)

    print(f"Wrote data:     {data_path}  ({len(data_df)} rows)")
    print(f"Wrote chart:    {chart_p}")
    print(f"Wrote findings: {findings_path}")
    print()
    print(data_df.sort_values("rest_differential_sum", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
