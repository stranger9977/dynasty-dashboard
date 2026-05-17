"""Revenge games 2026: fantasy-relevant players facing their former teams.

Cross-references 2024 and 2025 rosters to find QB/RB/WR/TE who switched teams,
then scans the 2026 schedule for matchups between current team and former team.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output

SLUG = "revenge_games"
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}


def find_team_switchers() -> pd.DataFrame:
    r24 = nflverse.load_rosters(2024)
    r25 = nflverse.load_rosters(2025)

    # Keep one row per gsis_id (rosters are already 1 row/player/season but be safe).
    r24 = r24.drop_duplicates(subset=["gsis_id"], keep="first")
    r25 = r25.drop_duplicates(subset=["gsis_id"], keep="first")

    cols24 = ["gsis_id", "full_name", "position", "team", "years_exp"]
    cols25 = ["gsis_id", "full_name", "position", "team", "years_exp"]

    merged = r24[cols24].merge(
        r25[cols25],
        on="gsis_id",
        suffixes=("_2024", "_2025"),
    )

    # Genuine team changes only.
    moved = merged[merged["team_2024"] != merged["team_2025"]].copy()

    # Filter to fantasy-relevant positions in BOTH seasons (drops position changes too).
    moved = moved[
        moved["position_2025"].isin(FANTASY_POSITIONS)
        & moved["position_2024"].isin(FANTASY_POSITIONS)
    ].copy()

    moved = moved.rename(
        columns={
            "team_2024": "former_team",
            "team_2025": "current_team",
            "position_2025": "position",
            "full_name_2025": "player_name",
            "years_exp_2025": "years_exp",
        }
    )

    return moved[
        [
            "gsis_id",
            "player_name",
            "position",
            "current_team",
            "former_team",
            "years_exp",
        ]
    ].reset_index(drop=True)


def find_revenge_games(switchers: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """For each switcher, find 2026 games where current team faces former team."""
    rows: list[dict] = []
    sched_cols = ["week", "gameday", "away_team", "home_team"]
    sched = schedule[sched_cols].copy()

    for _, p in switchers.iterrows():
        cur = p["current_team"]
        former = p["former_team"]
        mask = (
            ((sched["home_team"] == cur) & (sched["away_team"] == former))
            | ((sched["home_team"] == former) & (sched["away_team"] == cur))
        )
        matches = sched[mask]
        for _, g in matches.iterrows():
            # home/away from the former team's perspective (i.e. is the player
            # going home to face them, or are they coming to him?)
            former_is_home = g["home_team"] == former
            home_or_away = "away" if former_is_home else "home"
            rows.append(
                {
                    "player_name": p["player_name"],
                    "position": p["position"],
                    "current_team": cur,
                    "former_team": former,
                    "revenge_week": int(g["week"]),
                    "game_date": str(g["gameday"]),
                    "home_or_away": home_or_away,
                    "years_exp": int(p["years_exp"]) if pd.notna(p["years_exp"]) else 0,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        ["revenge_week", "position", "player_name"]
    ).reset_index(drop=True)


# Curated set of "marquee" players for findings highlights — recognizable names
# whose 2024→2025 move was notable in the fantasy/NFL news cycle.
MARQUEE_HINTS = {
    "QB": 8,  # most QBs are recognizable
    "RB": 5,
    "WR": 5,
    "TE": 4,
}


def build_chart(games: pd.DataFrame, path: Path) -> None:
    weeks = np.arange(1, 19)
    counts = games.groupby("revenge_week").size().reindex(weeks, fill_value=0)

    fig, ax = plt.subplots(figsize=(13, 7))
    bars = ax.bar(
        weeks,
        counts.values,
        color="#7a1f2b",
        edgecolor="#2a0a10",
        linewidth=0.8,
    )

    # Annotate each bar with top players in that week (prefer veterans, then QB/WR).
    pos_priority = {"QB": 0, "WR": 1, "RB": 2, "TE": 3}
    for wk, bar in zip(weeks, bars):
        wk_games = games[games["revenge_week"] == wk]
        if wk_games.empty:
            continue
        wk_sorted = wk_games.assign(
            _p=wk_games["position"].map(pos_priority).fillna(9),
            _y=-wk_games["years_exp"],
        ).sort_values(["_p", "_y"])
        names = wk_sorted["player_name"].head(3).tolist()
        label = "\n".join(names)
        ax.annotate(
            label,
            xy=(wk, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7,
            color="#1a1a1a",
        )
        ax.annotate(
            str(int(bar.get_height())),
            xy=(wk, bar.get_height() / 2),
            ha="center",
            va="center",
            fontsize=10,
            color="white",
            fontweight="bold",
        )

    ax.set_xticks(weeks)
    ax.set_xlabel("NFL Week (2026)")
    ax.set_ylabel("Number of revenge games")
    ax.set_title(
        "2026 Revenge Games by Week — QB/RB/WR/TE facing their 2024 team",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_ylim(0, max(counts.max() * 1.35, 5))
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def build_findings(games: pd.DataFrame) -> str:
    # Identify loaded week
    by_week = games.groupby("revenge_week").size().sort_values(ascending=False)
    loaded_week = int(by_week.index[0])
    loaded_count = int(by_week.iloc[0])

    # Pick 5-10 marquee names: sample across positions, biasing toward veterans
    # (years_exp is a decent proxy for "name recognition" since rookies are filtered
    # by the team-switch criterion already, and journeymen-vs-stars both have tenure).
    quota = {"QB": 3, "WR": 3, "RB": 3, "TE": 1}
    by_player = (
        games.sort_values("years_exp", ascending=False)
        .drop_duplicates(subset=["player_name"])
    )

    picks: list[pd.Series] = []
    for pos, n in quota.items():
        pos_rows = by_player[by_player["position"] == pos].head(n)
        for _, r in pos_rows.iterrows():
            picks.append(r)

    highlights = pd.DataFrame(picks).sort_values(
        ["revenge_week", "position"]
    ).head(10)

    bullets = []
    for _, r in highlights.iterrows():
        loc = "@" if r["home_or_away"] == "away" else "vs"
        bullets.append(
            f"- **{r['player_name']}** ({r['position']}, {r['current_team']}) "
            f"{loc} **{r['former_team']}** — Week {int(r['revenge_week'])} ({r['game_date']})"
        )
    bullets_md = "\n".join(bullets)

    total = len(games)
    unique_players = games["player_name"].nunique()

    # Position breakdown
    pos_counts = games["position"].value_counts().to_dict()
    pos_line = ", ".join(
        f"{pos}: {pos_counts.get(pos, 0)}" for pos in ["QB", "RB", "WR", "TE"]
    )

    return f"""# 2026 Revenge Games — Fantasy-Relevant Players vs. Former Teams

**Method:** Cross-referenced 2024 and 2025 nflverse rosters to identify QB/RB/WR/TE
who changed teams between seasons, then scanned the 2026 schedule for any matchup
between each player's current team and former team.

**Caveat:** The 2026 NFL season has not yet started, so we use **2025 rosters as a
proxy for 2026 rosters**. Some players will move again before Week 1 (cuts, late
trades, retirements), and rookies who joined a team in 2025 are not flagged as
"revenge" candidates since they have no prior NFL employer. Reader discretion
advised — treat each entry as a 2025→2026 carryover hypothesis.

## Headline numbers
- **{total} total revenge game-player pairs** across {unique_players} unique players.
- Position split — {pos_line}.
- **Most loaded revenge week: Week {loaded_week}** with **{loaded_count} fantasy
  revenge matchups** on the slate. Mark it on your DFS / start-sit calendar.

## Marquee revenge spots to circle
{bullets_md}

## How to use
Sort `data.parquet` by `revenge_week` to plan weekly start/sit narratives, or by
`position` if you're building one-week DFS angles. `home_or_away` is given from
the **player's** perspective: "away" means he travels back to face his old team,
"home" means his former team comes to him.
"""


def main() -> None:
    print("Loading rosters + schedule…")
    switchers = find_team_switchers()
    print(f"Found {len(switchers)} QB/RB/WR/TE team switchers (2024→2025).")

    schedule = nflverse.load_schedule_2026()
    games = find_revenge_games(switchers, schedule)
    print(f"Identified {len(games)} player-game revenge pairs in 2026.")

    # Persist
    data_path = output.write_data(SLUG, games)
    print(f"Wrote data → {data_path}")

    chart_p = output.chart_path(SLUG)
    build_chart(games, chart_p)
    print(f"Wrote chart → {chart_p} ({chart_p.stat().st_size} bytes)")

    findings_md = build_findings(games)
    findings_p = output.write_findings(SLUG, findings_md)
    print(f"Wrote findings → {findings_p}")


if __name__ == "__main__":
    main()
