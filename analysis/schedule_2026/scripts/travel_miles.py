"""Travel miles + time-zone shifts per team for the NFL 2026 schedule.

For each team's 17 games:
  - Determine if it's a true away game (neutral / international counts as travel
    for both teams).
  - Compute great-circle distance between team's home stadium and the actual
    game stadium.
  - Track timezone shift (UTC offsets at 2026-09-15 to avoid DST edge cases).

Per-team aggregates:
  - total_miles                — sum across all 17 games (home games = 0)
  - total_tz_shifts_abs        — sum of |tz_diff_hours| across away/neutral games
  - longest_single_trip_miles  — max one-way trip
  - longest_trip_destination   — stadium name for that longest trip
  - intl_miles                 — miles attributable to international games
  - back_to_back_long_trips    — count of consecutive weeks where both games
                                 are away with >1500 miles each

Run:
    cd /Users/nick/projects/dynasty-dashboard && \\
        uv run python analysis/schedule_2026/scripts/travel_miles.py
"""
from __future__ import annotations

import math
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "travel_miles"

# Fixed reference date for UTC-offset lookups (mid-September 2026 — DST in
# effect in US, also in Europe; avoids DST transition edge cases).
TZ_REF_DATE = datetime(2026, 9, 15, 12, 0)

LONG_TRIP_THRESHOLD = 1500.0  # miles


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3959.0  # earth radius in miles
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def utc_offset_hours(tz_name: str) -> float:
    """UTC offset in hours for a tz at the reference date. West of UTC = negative."""
    dt = TZ_REF_DATE.replace(tzinfo=ZoneInfo(tz_name))
    return dt.utcoffset().total_seconds() / 3600.0


def build_trip_rows(sched: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team) where the team had to travel (away or neutral)."""
    records: list[dict] = []
    for _, g in sched.iterrows():
        stadium = teams.resolve_stadium(g["stadium_id"], g["stadium"])
        stadium_name = g["stadium"]
        is_intl = stadium_name in teams.INTERNATIONAL
        for side in ("home", "away"):
            team = g[f"{side}_team"]
            opp = g["away_team"] if side == "home" else g["home_team"]
            neutral = teams.is_neutral_site(team, g["stadium_id"], stadium_name)
            if not neutral:
                # True home — no travel.
                records.append(
                    {
                        "game_id": g["game_id"],
                        "week": int(g["week"]),
                        "team": team,
                        "opp": opp,
                        "side": side,
                        "is_travel": False,
                        "is_intl": False,
                        "stadium_name": stadium.name,
                        "miles": 0.0,
                        "tz_diff_hours": 0.0,
                    }
                )
                continue

            home = teams.home_stadium(team)
            miles = haversine(home.lat, home.lon, stadium.lat, stadium.lon)
            # West→East = positive shift (lose hours); East→West = negative.
            tz_diff = utc_offset_hours(stadium.tz) - utc_offset_hours(home.tz)
            records.append(
                {
                    "game_id": g["game_id"],
                    "week": int(g["week"]),
                    "team": team,
                    "opp": opp,
                    "side": side,
                    "is_travel": True,
                    "is_intl": is_intl,
                    "stadium_name": stadium.name,
                    "miles": miles,
                    "tz_diff_hours": tz_diff,
                }
            )
    return pd.DataFrame(records)


def count_back_to_back_long_trips(team_rows: pd.DataFrame) -> int:
    """Count consecutive weeks where both games are away with >LONG_TRIP_THRESHOLD miles each."""
    # Sort by week. Note: there's a bye, so weeks aren't contiguous.
    tr = team_rows.sort_values("week").reset_index(drop=True)
    count = 0
    for i in range(len(tr) - 1):
        cur, nxt = tr.iloc[i], tr.iloc[i + 1]
        if (
            int(nxt["week"]) - int(cur["week"]) == 1
            and bool(cur["is_travel"])
            and bool(nxt["is_travel"])
            and float(cur["miles"]) > LONG_TRIP_THRESHOLD
            and float(nxt["miles"]) > LONG_TRIP_THRESHOLD
        ):
            count += 1
    return count


def build_summary(rows: pd.DataFrame) -> pd.DataFrame:
    out_records: list[dict] = []
    for team in teams.ALL_TEAMS:
        sub = rows[rows["team"] == team].copy()
        assert len(sub) == 17, f"{team} has {len(sub)} games, expected 17"

        travel = sub[sub["is_travel"]]
        if travel.empty:
            longest_miles = 0.0
            longest_dest = "—"
        else:
            longest_row = travel.loc[travel["miles"].idxmax()]
            longest_miles = float(longest_row["miles"])
            longest_dest = str(longest_row["stadium_name"])

        intl_miles = float(sub[sub["is_intl"]]["miles"].sum())
        total_miles = float(sub["miles"].sum())
        total_tz_shifts_abs = float(travel["tz_diff_hours"].abs().sum())
        b2b = count_back_to_back_long_trips(sub)

        out_records.append(
            {
                "team": team,
                "total_miles": total_miles,
                "total_tz_shifts_abs": total_tz_shifts_abs,
                "longest_single_trip_miles": longest_miles,
                "longest_trip_destination": longest_dest,
                "intl_miles": intl_miles,
                "back_to_back_long_trips": b2b,
            }
        )
    df = pd.DataFrame(out_records)
    return df


def make_chart(summary: pd.DataFrame, path) -> None:
    plot_df = summary.sort_values("total_miles", ascending=True).reset_index(drop=True)
    plot_df["domestic_miles"] = plot_df["total_miles"] - plot_df["intl_miles"]

    fig, ax = plt.subplots(figsize=(11, 11))
    y = np.arange(len(plot_df))

    # Stacked bars: domestic (steel blue) + international (crimson)
    ax.barh(
        y,
        plot_df["domestic_miles"],
        color="#4c72b0",
        edgecolor="black",
        linewidth=0.4,
        label="Domestic travel",
    )
    ax.barh(
        y,
        plot_df["intl_miles"],
        left=plot_df["domestic_miles"],
        color="#c44e52",
        edgecolor="black",
        linewidth=0.4,
        label="International travel",
    )

    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["team"], fontsize=9)
    ax.set_xlabel("Total travel miles (2026 regular season, home games = 0)")
    ax.set_title(
        "NFL 2026 — Total Travel Miles by Team\n"
        "(stacked: domestic + international games)"
    )

    xmax = float(plot_df["total_miles"].max())
    pad = xmax * 0.01 + 50

    for i, (total, intl, b2b) in enumerate(
        zip(plot_df["total_miles"], plot_df["intl_miles"], plot_df["back_to_back_long_trips"])
    ):
        label = f"{int(round(total)):,} mi"
        if intl > 0:
            label += f"  (intl {int(round(intl)):,})"
        if b2b > 0:
            label += f"  [B2B×{int(b2b)}]"
        ax.text(total + pad, i, label, va="center", ha="left", fontsize=8)

    ax.legend(loc="lower right", framealpha=0.9)
    ax.margins(x=0.20)
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _fmt_mi(x: float) -> str:
    return f"{int(round(x)):,}"


def build_findings(summary: pd.DataFrame, rows: pd.DataFrame) -> str:
    s = summary.copy()
    most = s.sort_values("total_miles", ascending=False).reset_index(drop=True)
    least = s.sort_values("total_miles", ascending=True).reset_index(drop=True)

    top1, top2, top3 = most.iloc[0], most.iloc[1], most.iloc[2]
    bot1, bot2, bot3 = least.iloc[0], least.iloc[1], least.iloc[2]

    intl_teams = s[s["intl_miles"] > 0].sort_values("intl_miles", ascending=False)
    intl_lines = [
        f"{r['team']} ({_fmt_mi(r['intl_miles'])} intl mi to {r['longest_trip_destination']})"
        for _, r in intl_teams.iterrows()
    ]

    b2b_df = s[s["back_to_back_long_trips"] > 0].sort_values(
        "back_to_back_long_trips", ascending=False
    )
    if not b2b_df.empty:
        b2b_lines = [
            f"{r['team']} ({int(r['back_to_back_long_trips'])})" for _, r in b2b_df.iterrows()
        ]
        b2b_str = (
            "Back-to-back long-trip stretches (>1,500 mi in consecutive weeks): "
            + ", ".join(b2b_lines) + "."
        )
    else:
        b2b_str = "No team faces back-to-back weeks of >1,500-mile trips in 2026."

    tz_leader = s.sort_values("total_tz_shifts_abs", ascending=False).iloc[0]

    league_total = s["total_miles"].sum()
    league_avg = league_total / 32

    md = f"""# Travel Miles & Time-Zone Shifts — 2026 Schedule

**Most-traveling teams.** {top1['team']} logs the heaviest mileage at
{_fmt_mi(top1['total_miles'])} miles, with its longest single trip a
{_fmt_mi(top1['longest_single_trip_miles'])}-mile haul to
{top1['longest_trip_destination']}. {top2['team']} ({_fmt_mi(top2['total_miles'])} mi)
and {top3['team']} ({_fmt_mi(top3['total_miles'])} mi) round out the top three.
For context, the league average is {_fmt_mi(league_avg)} miles per team.

**Least-traveling teams.** {bot1['team']} gets the lightest travel slate at
{_fmt_mi(bot1['total_miles'])} miles, followed by {bot2['team']}
({_fmt_mi(bot2['total_miles'])}) and {bot3['team']} ({_fmt_mi(bot3['total_miles'])}).
Geography rewards Northeast/Mid-Atlantic clubs whose AFC/NFC East road slates
are short hops.

**International participants ({len(intl_teams)} teams).** {'; '.join(intl_lines) if intl_lines else 'None.'}
These overseas games dominate each affected team's mileage column — a single
trans-Atlantic or trans-Pacific game adds 4,000–10,000+ miles round-trip
equivalent on the great-circle path.

**Time-zone burden.** {tz_leader['team']} accumulates the most absolute
time-zone shift hours at {tz_leader['total_tz_shifts_abs']:.1f}, reflecting
multiple cross-country (and possibly overseas) crossings.

**Back-to-back burdens.** {b2b_str}
"""
    return md


def main() -> None:
    sched = nflverse.load_schedule_2026()
    if "game_type" in sched.columns:
        sched = sched[sched["game_type"] == "REG"].copy()
    assert len(sched) == 272, f"expected 272 reg-season games, got {len(sched)}"

    rows = build_trip_rows(sched)
    assert len(rows) == 544, f"expected 544 team-game rows, got {len(rows)}"

    summary = build_summary(rows)
    assert len(summary) == 32, f"expected 32 teams, got {len(summary)}"

    # Order columns per spec
    data_df = summary[
        [
            "team",
            "total_miles",
            "total_tz_shifts_abs",
            "longest_single_trip_miles",
            "longest_trip_destination",
            "intl_miles",
            "back_to_back_long_trips",
        ]
    ].copy()

    data_path = output.write_data(SLUG, data_df)
    chart_p = output.chart_path(SLUG)
    make_chart(data_df, chart_p)
    findings_md = build_findings(data_df, rows)
    findings_path = output.write_findings(SLUG, findings_md)

    print(f"Wrote data:     {data_path}  ({len(data_df)} rows)")
    print(f"Wrote chart:    {chart_p}")
    print(f"Wrote findings: {findings_path}")
    print()
    print(
        data_df.sort_values("total_miles", ascending=False)
        .to_string(index=False, float_format=lambda x: f"{x:,.1f}")
    )


if __name__ == "__main__":
    main()
