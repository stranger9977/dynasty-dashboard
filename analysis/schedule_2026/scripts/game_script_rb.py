"""Game-script RB Strength-of-Schedule for 2026.

RBs benefit from positive game script (team leading -> more rush attempts, fewer
pass-script possessions). Project game-script from Vegas win totals:

  1. Implied home spread per game:
        home_spread = -(0.4 * (home_wt - away_wt) + 2.5)
     (negative spread means home favored; +2.5 = home-field advantage in points.)
     Neutral-site games get the HFA term zeroed.

  2. Logistic mapping spread -> win probability for the team:
        leading_share = 1 / (1 + exp(-team_point_advantage / 7))
     where team_point_advantage = -team_spread (positive if team favored).

  3. Per team, sum leading_share across 17 games. Higher = RB-friendly schedule.

Also tag each game as a positive-script game (team favored by >= 3) or
negative-script game (team is a >= 3-pt dog).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "game_script_rb"

# Spread model knobs.
WIN_DIFF_COEF = 0.4   # points of spread per win-total point of advantage
HFA_POINTS = 2.5      # home-field advantage (points)
LOGISTIC_SCALE = 7.0  # standard NFL spread->win-prob scale

# Thresholds for tagging a game as positive/negative game script.
SCRIPT_FAV_THRESHOLD = 3.0   # favored by >= 3 pts -> positive script
SCRIPT_DOG_THRESHOLD = -3.0  # dog by >= 3 pts -> negative script


def build_game_frame() -> pd.DataFrame:
    """Long frame: one row per (team, game) with spread + leading_share."""
    sched = nflverse.load_schedule_2026()
    wt = nflverse.load_win_totals_2026()
    if wt is None:
        raise RuntimeError("win_totals_2026.csv not found")

    wt_map = dict(zip(wt["team"], wt["win_total"]))

    rows = []
    for _, g in sched.iterrows():
        week = int(g["week"])
        home, away = g["home_team"], g["away_team"]
        home_wt = wt_map.get(home, np.nan)
        away_wt = wt_map.get(away, np.nan)
        is_neutral = (g.get("location") == "Neutral")

        hfa = 0.0 if is_neutral else HFA_POINTS
        # home_spread is negative when home is favored.
        home_spread = -(WIN_DIFF_COEF * (home_wt - away_wt) + hfa)
        away_spread = -home_spread

        # team_point_advantage > 0 means team is favored.
        home_adv = -home_spread
        away_adv = -away_spread

        home_lead = 1.0 / (1.0 + np.exp(-home_adv / LOGISTIC_SCALE))
        away_lead = 1.0 / (1.0 + np.exp(-away_adv / LOGISTIC_SCALE))

        rows.append({
            "team": home, "opp": away, "week": week, "is_home": True,
            "team_spread": home_spread, "team_point_advantage": home_adv,
            "leading_share": home_lead,
        })
        rows.append({
            "team": away, "opp": home, "week": week, "is_home": False,
            "team_spread": away_spread, "team_point_advantage": away_adv,
            "leading_share": away_lead,
        })

    return pd.DataFrame(rows)


def compute_team_table(games_df: pd.DataFrame) -> pd.DataFrame:
    wt = nflverse.load_win_totals_2026()
    wt_map = dict(zip(wt["team"], wt["win_total"]))

    rows = []
    for team in teams.ALL_TEAMS:
        td = games_df[games_df["team"] == team]
        total_leading = float(td["leading_share"].sum())
        avg_spread = float(td["team_spread"].mean())
        pos_games = int((td["team_point_advantage"] >= SCRIPT_FAV_THRESHOLD).sum())
        neg_games = int((td["team_point_advantage"] <= SCRIPT_DOG_THRESHOLD).sum())
        rows.append({
            "team": team,
            "win_total": float(wt_map.get(team, np.nan)),
            "total_leading_share": round(total_leading, 3),
            "avg_implied_spread": round(avg_spread, 3),
            "positive_script_games_count": pos_games,
            "negative_script_games_count": neg_games,
        })
    df = (
        pd.DataFrame(rows)
        .sort_values("total_leading_share", ascending=False)
        .reset_index(drop=True)
    )
    return df


def plot_bar(df: pd.DataFrame, path) -> None:
    d = df.sort_values("total_leading_share", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 11))

    # Color gradient by total_leading_share (higher = greener, lower = redder).
    vals = d["total_leading_share"].to_numpy()
    vmin, vmax = vals.min(), vals.max()
    norm = (vals - vmin) / (vmax - vmin) if vmax > vmin else np.zeros_like(vals)
    cmap = plt.get_cmap("RdYlGn")
    colors = [cmap(v) for v in norm]

    ax.barh(d["team"], vals, color=colors, edgecolor="black", linewidth=0.4)

    # Annotate with leading_share and (pos / neg) game counts.
    for i, row in d.iterrows():
        ax.text(
            row["total_leading_share"] + 0.05,
            i,
            f"{row['total_leading_share']:.2f}  "
            f"(+{row['positive_script_games_count']} / "
            f"-{row['negative_script_games_count']})",
            va="center",
            fontsize=8,
        )

    ax.axvline(8.5, color="gray", linestyle="--", alpha=0.5,
               label="Neutral (8.5 of 17 games leading)")
    ax.set_xlabel("Sum of expected leading-game-share across 17 games", fontsize=11)
    ax.set_title(
        "NFL 2026 Game-Script RB SoS\n"
        "Higher = more expected 'team leading' = RB-friendly schedule\n"
        "Annotations: total_leading_share  (+favored / -underdog) games at >=3 pts",
        fontsize=12,
    )
    ax.grid(True, alpha=0.25, axis="x")
    ax.set_xlim(0, max(vals) + 1.5)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


# Light RB-room context for the findings prose. Kept short on purpose.
RB_ROOMS: dict[str, str] = {
    "BAL": "Derrick Henry + Justice Hill",
    "PHI": "Saquon Barkley",
    "DET": "Jahmyr Gibbs + David Montgomery",
    "BUF": "James Cook",
    "GB": "Josh Jacobs",
    "KC": "Isiah Pacheco / Kareem Hunt committee",
    "SF": "Christian McCaffrey",
    "LA": "Kyren Williams + Blake Corum",
    "SEA": "Kenneth Walker + Zach Charbonnet",
    "HOU": "Joe Mixon / Nick Chubb",
    "NE": "Rhamondre Stevenson + TreVeyon Henderson",
    "DEN": "JK Dobbins / RJ Harvey",
    "LAC": "Najee Harris / Omarion Hampton",
    "CHI": "D'Andre Swift + Kyle Monangai",
    "CIN": "Chase Brown",
    "DAL": "Javonte Williams committee",
    "JAX": "Travis Etienne / Tank Bigsby",
    "TB": "Bucky Irving + Rachaad White",
    "PIT": "Jaylen Warren / Kaleb Johnson",
    "MIN": "Jordan Mason / Aaron Jones",
    "NYG": "Tyrone Tracy / Cam Skattebo",
    "NO": "Alvin Kamara + Kendre Miller",
    "CAR": "Chuba Hubbard + Jonathon Brooks",
    "WAS": "Brian Robinson / Austin Ekeler",
    "IND": "Jonathan Taylor",
    "TEN": "Tony Pollard / Tyjae Spears",
    "ATL": "Bijan Robinson",
    "CLE": "Jerome Ford / Quinshon Judkins",
    "LV": "Ashton Jeanty",
    "NYJ": "Breece Hall",
    "ARI": "James Conner / Trey Benson",
    "MIA": "De'Von Achane + Jaylen Wright",
}


def build_findings(df: pd.DataFrame) -> str:
    top5 = df.head(5).copy()
    bot5 = df.tail(5).sort_values("total_leading_share").copy()

    def line(r: pd.Series) -> str:
        room = RB_ROOMS.get(r["team"], "")
        room_str = f" — {room}" if room else ""
        return (
            f"- **{r['team']}**{room_str}: "
            f"leading-share **{r['total_leading_share']:.2f}**, "
            f"avg spread **{r['avg_implied_spread']:+.2f}**, "
            f"**{int(r['positive_script_games_count'])}** games as a 3+pt favorite "
            f"vs **{int(r['negative_script_games_count'])}** as a 3+pt dog"
        )

    top_lines = "\n".join(line(r) for _, r in top5.iterrows())
    bot_lines = "\n".join(line(r) for _, r in bot5.iterrows())

    leader = top5.iloc[0]
    worst = bot5.iloc[0]
    median_share = float(df["total_leading_share"].median())

    md = f"""# Game-Script RB SoS — 2026

This view ranks each NFL team's 2026 schedule by **expected positive game
script** for their RBs. For every game we derive an implied spread from Vegas
win totals (0.4 pts per win-total delta, +2.5 home-field), then convert that
spread into a logistic win probability — the "expected leading share". Summed
across 17 games it estimates how many games each team should spend in the
positive-script (ahead-on-the-scoreboard) state where rush volume and red-zone
carries concentrate. Median across the league is **{median_share:.2f}**.

## Best RB game-script schedules

These rooms project for the most ahead-and-running snaps; volume-driven RBs
here are the cleanest **bell-cow candidates** in 2026.

{top_lines}

## Worst RB game-script schedules

These teams will trail more often, capping carry volume and tilting their
backfields toward **pass-down / passing-game** roles (receiving backs benefit
relative to early-down grinders).

{bot_lines}

## Read

**{leader['team']}'s** RBs ({RB_ROOMS.get(leader['team'], 'backfield')}) benefit
most from positive game script — **{int(leader['positive_script_games_count'])}**
of 17 games projected as 3+pt favorites and an average implied spread of
**{leader['avg_implied_spread']:+.2f}**. Conversely, **{worst['team']}**
({RB_ROOMS.get(worst['team'], 'backfield')}) has the league's worst
projection — only **{int(worst['positive_script_games_count'])}** favored
games against **{int(worst['negative_script_games_count'])}** as a 3+pt
underdog, with an average implied spread of
**{worst['avg_implied_spread']:+.2f}** — early-down workhorses there should be
faded versus their ADP and pass-catching backs should be priced up.
"""
    return md


def main() -> None:
    games_df = build_game_frame()
    table = compute_team_table(games_df)
    assert len(table) == 32, f"expected 32 teams, got {len(table)}"

    data_path = output.write_data(SLUG, table)
    chart_p = output.chart_path(SLUG)
    plot_bar(table, chart_p)
    findings_path = output.write_findings(SLUG, build_findings(table))

    print(f"wrote {data_path}")
    print(f"wrote {chart_p}")
    print(f"wrote {findings_path}")
    print()
    print("=== top 5 RB-friendly game scripts ===")
    print(table.head(5).to_string(index=False))
    print()
    print("=== bottom 5 RB-friendly game scripts ===")
    print(table.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
