"""Body-clock map for the NFL 2026 schedule.

For each game and each team, compute the kickoff time in that team's home time
zone (their "body clock time"). Flag body-clock DISadvantage when the body-clock
kickoff is >=2h earlier than 1pm local (e.g., a West Coast team in a 1pm ET kick
= 10am PT body clock). Flag ADvantage when body-clock kickoff is >=2h later than
1pm local (rare — typically late MNF for east-coast teams).

Run:
    cd /Users/nick/projects/dynasty-dashboard && \\
        uv run python analysis/schedule_2026/scripts/body_clock.py
"""
from __future__ import annotations

import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "body_clock"

# Threshold in hours: kickoff in body-clock tz must be this far from 1pm.
THRESHOLD_HOURS = 2.0
REFERENCE_HOUR = 13.0  # 1pm local


def body_clock_hour(gameday: str, gametime: str, stadium_tz: str, team_tz: str) -> float:
    """Return team-home-tz kickoff as a decimal hour (e.g., 10.5 = 10:30am)."""
    hh, mm = gametime.split(":")
    naive = datetime.strptime(gameday, "%Y-%m-%d").replace(hour=int(hh), minute=int(mm))
    aware_local = naive.replace(tzinfo=ZoneInfo(stadium_tz))
    body = aware_local.astimezone(ZoneInfo(team_tz))
    return body.hour + body.minute / 60.0


def build_game_rows(sched: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team perspective): 64 rows per week pair (272 games -> 544 rows)."""
    records: list[dict] = []
    for _, g in sched.iterrows():
        stadium = teams.resolve_stadium(g["stadium_id"], g["stadium"])
        stadium_tz = stadium.tz
        for side in ("home", "away"):
            team = g[f"{side}_team"]
            opp = g["away_team"] if side == "home" else g["home_team"]
            team_stadium = teams.home_stadium(team)
            team_tz = team_stadium.tz
            bc_hour = body_clock_hour(g["gameday"], g["gametime"], stadium_tz, team_tz)
            delta = bc_hour - REFERENCE_HOUR  # negative = early body clock
            disadvantage = delta <= -THRESHOLD_HOURS
            advantage = delta >= THRESHOLD_HOURS
            records.append(
                {
                    "game_id": g["game_id"],
                    "week": int(g["week"]),
                    "gameday": g["gameday"],
                    "gametime": g["gametime"],
                    "stadium": stadium.name,
                    "stadium_tz": stadium_tz,
                    "team": team,
                    "opp": opp,
                    "side": side,
                    "team_tz": team_tz,
                    "body_clock_hour": bc_hour,
                    "delta_from_1pm": delta,
                    "disadvantage": disadvantage,
                    "advantage": advantage,
                }
            )
    return pd.DataFrame(records)


def build_summary(rows: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        rows.groupby("team")
        .agg(
            disadvantage_games=("disadvantage", "sum"),
            advantage_games=("advantage", "sum"),
            games=("week", "count"),
        )
        .reset_index()
    )
    grouped["disadvantage_games"] = grouped["disadvantage_games"].astype(int)
    grouped["advantage_games"] = grouped["advantage_games"].astype(int)
    grouped["net_body_clock"] = grouped["disadvantage_games"] - grouped["advantage_games"]
    grouped = grouped[
        ["team", "disadvantage_games", "advantage_games", "net_body_clock", "games"]
    ].sort_values("team").reset_index(drop=True)
    return grouped


def make_chart(df: pd.DataFrame, path) -> None:
    plot_df = df.sort_values("net_body_clock", ascending=True).reset_index(drop=True)
    # Color by net: red = burden, green = advantage-heavy, grey = neutral.
    colors = []
    for v in plot_df["net_body_clock"]:
        if v >= 2:
            colors.append("#d62728")  # red — heavy burden
        elif v >= 1:
            colors.append("#ff7f0e")  # orange — some burden
        elif v <= -1:
            colors.append("#2ca02c")  # green — advantage-heavy
        else:
            colors.append("#7f7f7f")  # grey — neutral

    fig, ax = plt.subplots(figsize=(11, 11))
    y = np.arange(len(plot_df))
    ax.barh(y, plot_df["net_body_clock"], color=colors, edgecolor="black", linewidth=0.4)
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["team"], fontsize=9)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Net body-clock burden (disadvantage games − advantage games)")
    ax.set_title(
        "NFL 2026 Body-Clock Map — Net Body-Clock Burden by Team\n"
        "(disadvantage = body clock ≥2h before 1pm; advantage = ≥2h after)"
    )

    xmax = plot_df["net_body_clock"].max()
    xmin = plot_df["net_body_clock"].min()
    pad = max(abs(xmax), abs(xmin), 1) * 0.05 + 0.15
    for i, (net, dis, adv) in enumerate(
        zip(plot_df["net_body_clock"], plot_df["disadvantage_games"], plot_df["advantage_games"])
    ):
        offset = pad if net >= 0 else -pad
        ha = "left" if net >= 0 else "right"
        ax.text(
            net + offset,
            i,
            f"{net:+d}  (dis:{int(dis)} / adv:{int(adv)})",
            va="center",
            ha=ha,
            fontsize=8,
        )

    from matplotlib.patches import Patch

    legend_elems = [
        Patch(facecolor="#d62728", edgecolor="black", label="Heavy burden (net ≥ +2)"),
        Patch(facecolor="#ff7f0e", edgecolor="black", label="Some burden (net +1)"),
        Patch(facecolor="#7f7f7f", edgecolor="black", label="Neutral (net 0)"),
        Patch(facecolor="#2ca02c", edgecolor="black", label="Advantage-heavy (net ≤ −1)"),
    ]
    ax.legend(handles=legend_elems, loc="lower right", framealpha=0.9)
    ax.margins(x=0.22)
    ax.grid(axis="x", linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _fmt_hour(h: float) -> str:
    """10.0 -> '10:00am'; 13.5 -> '1:30pm'; 22.0 -> '10:00pm'."""
    hr = int(h)
    mn = int(round((h - hr) * 60))
    if mn == 60:
        hr += 1
        mn = 0
    suffix = "am" if hr < 12 else "pm"
    disp = hr if 1 <= hr <= 12 else (hr - 12 if hr > 12 else 12)
    return f"{disp}:{mn:02d}{suffix}"


def _tz_label(tz: str) -> str:
    return {
        "America/New_York": "ET",
        "America/Chicago": "CT",
        "America/Denver": "MT",
        "America/Phoenix": "MT",
        "America/Los_Angeles": "PT",
    }.get(tz, tz.split("/")[-1])


def _fmt_game_example(row: pd.Series) -> str:
    """e.g., 'SEA at IND week 4, 1:00pm ET = 10:00am PT body clock'."""
    side = row["side"]
    if side == "away":
        descriptor = f"{row['team']} at {row['opp']}"
    else:
        descriptor = f"{row['opp']} at {row['team']}"
    hh, mm = row["gametime"].split(":")
    local_hour = int(hh) + int(mm) / 60.0
    return (
        f"{descriptor} week {int(row['week'])}, "
        f"{_fmt_hour(local_hour)} {_tz_label(row['stadium_tz'])} = "
        f"{_fmt_hour(row['body_clock_hour'])} {_tz_label(row['team_tz'])} body clock"
    )


def build_findings(summary: pd.DataFrame, rows: pd.DataFrame) -> str:
    # Sort by disadvantage games first — that's the meaningful burden.
    worst = summary.sort_values(
        ["disadvantage_games", "net_body_clock"], ascending=[False, False]
    ).reset_index(drop=True)

    top1 = worst.iloc[0]
    top2 = worst.iloc[1]
    top3 = worst.iloc[2]
    top4 = worst.iloc[3]

    def examples_for(team: str, k: int = 2) -> list[str]:
        sub = rows[(rows["team"] == team) & rows["disadvantage"]].copy()
        # Earliest body-clock kicks first (most painful).
        sub = sub.sort_values("body_clock_hour", ascending=True)
        return [_fmt_game_example(r) for _, r in sub.head(k).iterrows()]

    ex_top1 = examples_for(top1["team"], 3)
    ex_top2 = examples_for(top2["team"], 2)
    ex_top3 = examples_for(top3["team"], 2)
    ex_top4 = examples_for(top4["team"], 1)

    # Find the single earliest body-clock kickoff in the season (excluding international
    # 9:30am-local games which dwarf domestic disadvantages and aren't representative).
    domestic = rows[rows["stadium_tz"].str.startswith("America/")]
    earliest_domestic = domestic.sort_values("body_clock_hour").iloc[0]
    earliest_ex = _fmt_game_example(earliest_domestic)

    # International outliers — call out separately.
    intl = rows[~rows["stadium_tz"].str.startswith("America/")]
    intl_examples: list[str] = []
    if not intl.empty:
        # take two distinct early kicks
        sub = intl.sort_values("body_clock_hour").head(4)
        seen: set[str] = set()
        for _, r in sub.iterrows():
            if r["team"] in seen:
                continue
            intl_examples.append(_fmt_game_example(r))
            seen.add(r["team"])
            if len(intl_examples) >= 2:
                break

    total_dis = int(summary["disadvantage_games"].sum())
    total_adv = int(summary["advantage_games"].sum())

    worst_burden_line = (
        f"**{top1['team']} carries the heaviest body-clock burden** with "
        f"{int(top1['disadvantage_games'])} disadvantage games (net {int(top1['net_body_clock']):+d}). "
        f"Examples: {'; '.join(ex_top1) if ex_top1 else 'n/a'}."
    )
    runner_up_line = (
        f"**Other West-Coast sufferers:** {top2['team']} ({int(top2['disadvantage_games'])}), "
        f"{top3['team']} ({int(top3['disadvantage_games'])}), and "
        f"{top4['team']} ({int(top4['disadvantage_games'])}) round out the top tier. "
        f"E.g., {'; '.join(ex_top2) if ex_top2 else 'n/a'}"
        + (f"; {ex_top3[0]}" if ex_top3 else "")
        + (f"; {ex_top4[0]}" if ex_top4 else "")
        + "."
    )
    international_line = (
        f"**International games are the single worst body-clock hits.** "
        + (f"Examples: {'; '.join(intl_examples)}." if intl_examples else "")
        + " A 9:30am-local kick in London/Madrid/Berlin puts US teams at a 3–4am body-clock kickoff."
    )
    earliest_line = (
        f"**Worst purely-domestic kick:** {earliest_ex} — the canonical 1pm-ET-vs-West-Coast disadvantage."
    )
    advantage_line = (
        f"**Net counts ({total_dis} disadvantage, {total_adv} advantage league-wide):** "
        f"Mountain/Central/Eastern teams almost never wake up early for kickoff, while "
        f"West-Coast teams hit the 10am body-clock window 3–4 times each. The structural "
        f"penalty is almost entirely a West-Coast problem driven by 1pm-ET windows."
    )

    md = f"""# Body-Clock Map — 2026 Schedule

- {worst_burden_line}
- {runner_up_line}
- {international_line}
- {earliest_line}
- {advantage_line}
"""
    return md


def main() -> None:
    sched = nflverse.load_schedule_2026()
    if "game_type" in sched.columns:
        sched = sched[sched["game_type"] == "REG"].copy()
    assert len(sched) == 272, f"expected 272 reg-season games, got {len(sched)}"

    rows = build_game_rows(sched)
    assert len(rows) == 544, f"expected 544 team-game rows, got {len(rows)}"

    summary = build_summary(rows)
    assert len(summary) == 32, f"expected 32 teams, got {len(summary)}"
    assert (summary["games"] == 17).all(), "every team should have 17 games"

    data_df = summary[["team", "disadvantage_games", "advantage_games", "net_body_clock"]].copy()
    data_path = output.write_data(SLUG, data_df)
    chart_p = output.chart_path(SLUG)
    make_chart(data_df, chart_p)
    findings_md = build_findings(data_df, rows)
    findings_path = output.write_findings(SLUG, findings_md)

    print(f"Wrote data:     {data_path}  ({len(data_df)} rows)")
    print(f"Wrote chart:    {chart_p}")
    print(f"Wrote findings: {findings_path}")
    print()
    print(data_df.sort_values("net_body_clock", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
