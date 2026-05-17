"""Pace x opponent pace projected play volume for 2026.

Fantasy points = volume * efficiency. Volume comes from total plays in a game,
and both offense and defense pace contribute. Some teams snap quickly (high
offensive plays/game); some defenses surrender many plays (slow off the field).

Method:
  1. From PBP 2024-2025 (regular season), compute per-team:
       off_plays_per_game  = mean plays/game where team is the posteam
       def_plays_allowed   = mean plays/game where team is the defteam
     Weight 2025 = 0.70, 2024 = 0.30.
  2. For each 2026 game, blended per-team pace =
       0.5 * team.off_plays_per_game  +  0.5 * opp.def_plays_allowed
     (i.e. the team's own tempo meets the opponent's defensive tempo).
  3. Aggregate the 17 per-game projections per team for season totals.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "pace_volume"

OFF_PLAY_TYPES = ("pass", "run")
# 3-season recency-weighted baseline (more stable than 2-year)
SEASON_WEIGHTS = {2025: 0.50, 2024: 0.30, 2023: 0.20}
# Vegas tilt: how much combined-WT swings the per-game pace projection.
# (combined_WT - league_avg_combined) × VEGAS_TILT_COEF = pct adjustment.
# 0.012 → roughly +4-5% on a 22-WT game vs a 12-WT game.
VEGAS_TILT_COEF = 0.012


def compute_historical_pace() -> pd.DataFrame:
    """Per-team blended off plays/game and def plays allowed/game, 3-season weighted."""
    pbp = nflverse.load_pbp(seasons=list(SEASON_WEIGHTS.keys()))
    pbp = pbp[pbp["season_type"] == "REG"]
    pbp = pbp[pbp["play_type"].isin(OFF_PLAY_TYPES)]

    # Offensive plays per team per game per season.
    off = (
        pbp.groupby(["season", "posteam", "game_id"])
        .size()
        .reset_index(name="plays")
        .groupby(["season", "posteam"])["plays"]
        .mean()
        .reset_index()
        .rename(columns={"posteam": "team", "plays": "off_plays_per_game"})
    )

    # Defensive plays allowed per team per game per season.
    deff = (
        pbp.groupby(["season", "defteam", "game_id"])
        .size()
        .reset_index(name="plays")
        .groupby(["season", "defteam"])["plays"]
        .mean()
        .reset_index()
        .rename(columns={"defteam": "team", "plays": "def_plays_allowed_per_game"})
    )

    merged = off.merge(deff, on=["season", "team"], how="outer")

    # Weighted blend across 3 seasons. SEASON_WEIGHTS already sums to 1.0 with
    # all seasons present; normalize within each team to handle missing seasons.
    rows = []
    for team in teams.ALL_TEAMS:
        sub = merged[merged["team"] == team]
        off_blended = def_blended = off_w = def_w = 0.0
        for season, w in SEASON_WEIGHTS.items():
            r = sub[sub["season"] == season]
            if r.empty:
                continue
            ov, dv = r["off_plays_per_game"].iloc[0], r["def_plays_allowed_per_game"].iloc[0]
            if pd.notna(ov):
                off_blended += w * ov
                off_w += w
            if pd.notna(dv):
                def_blended += w * dv
                def_w += w
        rows.append({
            "team": team,
            "off_plays_per_game": off_blended / off_w if off_w > 0 else np.nan,
            "def_plays_allowed_per_game": def_blended / def_w if def_w > 0 else np.nan,
        })
    return pd.DataFrame(rows)


def project_2026(hist: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (team_summary_df, weekly_df).

    weekly_df: one row per (team, week) with projected offensive plays.
    team_summary_df: 32 rows with historical pace + 2026 projections.
    """
    sched = nflverse.load_schedule_2026()
    off_map = dict(zip(hist["team"], hist["off_plays_per_game"]))
    def_map = dict(zip(hist["team"], hist["def_plays_allowed_per_game"]))

    # Vegas-tilt: combined win totals as a proxy for expected game pace
    wt = nflverse.load_win_totals_2026()
    wt_map = dict(zip(wt["team"], wt["win_total"]))
    league_avg_combined = 2 * wt["win_total"].mean()  # avg pairwise sum

    rows = []
    for _, g in sched.iterrows():
        week = int(g["week"])
        home, away = g["home_team"], g["away_team"]
        # Base pace blend
        home_base = 0.5 * off_map[home] + 0.5 * def_map[away]
        away_base = 0.5 * off_map[away] + 0.5 * def_map[home]
        # Vegas tilt — high-WT matchups skew slightly upward in play volume
        combined_wt = wt_map.get(home, 8.5) + wt_map.get(away, 8.5)
        tilt = 1.0 + VEGAS_TILT_COEF * (combined_wt - league_avg_combined)
        home_proj = home_base * tilt
        away_proj = away_base * tilt
        rows.append({"team": home, "week": week, "opp": away,
                     "projected_off_plays": home_proj, "vegas_tilt": tilt})
        rows.append({"team": away, "week": week, "opp": home,
                     "projected_off_plays": away_proj, "vegas_tilt": tilt})
    weekly = pd.DataFrame(rows)

    # Per-team aggregates.
    summary_rows = []
    for team in teams.ALL_TEAMS:
        td = weekly[weekly["team"] == team]
        total = float(td["projected_off_plays"].sum())
        avg = float(td["projected_off_plays"].mean())
        summary_rows.append({
            "team": team,
            "off_plays_per_game": round(float(off_map[team]), 3),
            "def_plays_allowed_per_game": round(float(def_map[team]), 3),
            "projected_2026_total_plays": round(total, 2),
            "projected_2026_avg_plays_per_game": round(avg, 3),
            "n_games": int(len(td)),
        })
    summary = pd.DataFrame(summary_rows).sort_values(
        "projected_2026_total_plays", ascending=False
    ).reset_index(drop=True)
    return summary, weekly


def plot_chart(summary: pd.DataFrame, path) -> None:
    df = summary.sort_values("projected_2026_total_plays", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 11))

    values = df["projected_2026_total_plays"].to_numpy()
    teams_list = df["team"].tolist()

    # Color gradient: green for high volume (good for fantasy), red for low.
    vmin, vmax = values.min(), values.max()
    norm = (values - vmin) / (vmax - vmin) if vmax > vmin else np.zeros_like(values)
    colors = plt.cm.RdYlGn(norm)

    bars = ax.barh(teams_list, values, color=colors, edgecolor="black", linewidth=0.5)

    # Annotate each bar with the value.
    for bar, v, avg in zip(bars, values, df["projected_2026_avg_plays_per_game"]):
        ax.text(
            bar.get_width() + 2,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.0f}  ({avg:.1f}/g)",
            va="center",
            ha="left",
            fontsize=8.5,
        )

    league_avg = float(values.mean())
    ax.axvline(league_avg, color="black", linestyle="--", alpha=0.4,
               label=f"league avg = {league_avg:.0f}")

    ax.set_xlabel("Projected 2026 total offensive plays (17 games)", fontsize=11)
    ax.set_title(
        "NFL 2026 Projected Offensive Play Volume\n"
        "Blended team pace x opponent defensive pace (2024-2025 weighted)",
        fontsize=12,
    )
    ax.set_xlim(values.min() - 20, values.max() + 60)
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)

    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def build_findings(summary: pd.DataFrame) -> str:
    top = summary.head(5)
    bottom = summary.tail(5).iloc[::-1]  # reverse so worst is last

    def fmt(r) -> str:
        return (
            f"- **{r['team']}** — {r['projected_2026_total_plays']:.0f} total plays "
            f"({r['projected_2026_avg_plays_per_game']:.1f}/g); "
            f"own pace {r['off_plays_per_game']:.1f}/g, "
            f"opp def pace {r['def_plays_allowed_per_game']:.1f}/g allowed"
        )

    top_lines = "\n".join(fmt(r) for _, r in top.iterrows())
    bot_lines = "\n".join(fmt(r) for _, r in bottom.iterrows())

    league_avg_total = float(summary["projected_2026_total_plays"].mean())
    league_avg_per_g = float(summary["projected_2026_avg_plays_per_game"].mean())
    spread = (
        summary["projected_2026_total_plays"].max()
        - summary["projected_2026_total_plays"].min()
    )

    headline_high = summary.iloc[0]
    headline_low = summary.iloc[-1]

    md = f"""# Pace x Opponent Pace — Projected 2026 Play Volume

Fantasy production is **volume x efficiency**, and volume is just plays. We
blend each team's 2024-2025 offensive plays/game (70/30 weighted toward 2025)
with each weekly opponent's defensive plays allowed/game to project total
offensive snaps across the 17-game slate. League average lands at
**{league_avg_total:.0f}** plays ({league_avg_per_g:.1f}/g); the gap between
the highest- and lowest-volume schedule is **{spread:.0f}** plays.

## Highest-volume schedules (fantasy upside)

{top_lines}

**{headline_high['team']}** tops the league at **{headline_high['projected_2026_total_plays']:.0f}**
projected plays ({headline_high['projected_2026_avg_plays_per_game']:.1f}/g) — their own
{headline_high['off_plays_per_game']:.1f}-snap-per-game offense meeting opponents who
historically surrender heavy volume. RB and pass-catcher floors get a real
boost here just from raw touch count.

## Lowest-volume schedules (volume drag)

{bot_lines}

**{headline_low['team']}** brings up the rear at **{headline_low['projected_2026_total_plays']:.0f}**
projected plays ({headline_low['projected_2026_avg_plays_per_game']:.1f}/g) — own offense
runs {headline_low['off_plays_per_game']:.1f}/g and the schedule pairs them with
defenses that limit volume ({headline_low['def_plays_allowed_per_game']:.1f}/g allowed
by their opponents on average). Bake a touch-count discount into rankings.

## Read

Pace + matchup compounds: the leaders combine an already-uptempo offense with
opponents who play fast or get gashed on defense, while the laggards stack a
plodding base rate against ball-controlling foes. Worth roughly a
**{(spread / 17):.1f}** plays/game swing top-to-bottom — meaningful at the
margins for RB/WR weekly floors and for streaming defenses.
"""
    return md


def main() -> None:
    hist = compute_historical_pace()
    summary, weekly = project_2026(hist)
    assert len(summary) == 32, f"expected 32 teams, got {len(summary)}"

    # Write the team summary as the primary data artifact.
    data_path = output.write_data(SLUG, summary)
    # Also persist the weekly per-team pace projections.
    weekly_path = output.write_data(SLUG, weekly, filename="weekly.parquet")

    chart_p = output.chart_path(SLUG)
    plot_chart(summary, chart_p)
    findings_path = output.write_findings(SLUG, build_findings(summary))

    print(f"wrote {data_path}")
    print(f"wrote {weekly_path}")
    print(f"wrote {chart_p}")
    print(f"wrote {findings_path}")
    print()
    print("=== top 5 highest projected play volume ===")
    print(summary.head(5).to_string(index=False))
    print()
    print("=== bottom 5 lowest projected play volume ===")
    print(summary.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
