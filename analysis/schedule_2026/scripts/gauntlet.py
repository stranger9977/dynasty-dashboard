"""Gauntlet detector — find 3+ consecutive-week stretches against top/bottom-tier
opponents in the 2026 NFL schedule. Writes data.parquet, chart.png, findings.md.

Run: uv run python analysis/schedule_2026/scripts/gauntlet.py
"""
from __future__ import annotations

import sys
sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from _shared import nflverse, teams, output

SLUG = "gauntlet"
MIN_STREAK = 3
HARD_WINDOW = 4  # weeks


def build_team_week_table(schedule: pd.DataFrame) -> pd.DataFrame:
    """Return long-form table: one row per (team, week) with opponent (or None for bye)."""
    rows = []
    for _, g in schedule.iterrows():
        rows.append({"team": g["home_team"], "week": int(g["week"]), "opp": g["away_team"]})
        rows.append({"team": g["away_team"], "week": int(g["week"]), "opp": g["home_team"]})
    df = pd.DataFrame(rows)

    weeks = sorted(df["week"].unique())
    full = pd.MultiIndex.from_product([teams.ALL_TEAMS, weeks], names=["team", "week"]).to_frame(index=False)
    df = full.merge(df, on=["team", "week"], how="left")
    return df.sort_values(["team", "week"]).reset_index(drop=True)


def assign_tiers(win_totals: pd.DataFrame) -> tuple[set[str], set[str], dict[str, float]]:
    wt = win_totals.sort_values("win_total", ascending=False).reset_index(drop=True)
    top = set(wt.head(10)["team"].tolist())
    bottom = set(wt.tail(10)["team"].tolist())
    wt_map = dict(zip(wt["team"], wt["win_total"]))
    return top, bottom, wt_map


def find_streaks(weeks_with_membership: list[tuple[int, str, bool]], min_len: int = MIN_STREAK):
    """Given an ordered list of (week, opp_or_None, in_tier), find streaks of length >= min_len.

    A bye breaks a streak. A non-tier opponent breaks a streak.
    """
    streaks = []
    cur = []
    for week, opp, in_tier in weeks_with_membership:
        if in_tier and opp is not None:
            cur.append((week, opp))
        else:
            if len(cur) >= min_len:
                streaks.append(cur)
            cur = []
    if len(cur) >= min_len:
        streaks.append(cur)
    return streaks


def summarize_team(team: str, tw: pd.DataFrame, top: set[str], bottom: set[str]) -> dict:
    tw = tw[tw["team"] == team].sort_values("week")
    top_seq = [(int(r["week"]), r["opp"], (r["opp"] in top) if isinstance(r["opp"], str) else False) for _, r in tw.iterrows()]
    bot_seq = [(int(r["week"]), r["opp"], (r["opp"] in bottom) if isinstance(r["opp"], str) else False) for _, r in tw.iterrows()]
    gauntlets = find_streaks(top_seq)
    easies = find_streaks(bot_seq)

    def to_dicts(stretches):
        out = []
        for s in stretches:
            out.append({
                "start_week": s[0][0],
                "end_week": s[-1][0],
                "length": len(s),
                "opponents": ",".join(opp for _, opp in s),
            })
        return out

    g_dicts = to_dicts(gauntlets)
    e_dicts = to_dicts(easies)
    longest = max((d["length"] for d in g_dicts), default=0)
    g_weeks_total = sum(d["length"] for d in g_dicts)
    e_weeks_total = sum(d["length"] for d in e_dicts)

    def fmt_stretch(d):
        return f"W{d['start_week']}-{d['end_week']} ({d['length']}): {d['opponents']}"

    return {
        "team": team,
        "gauntlets": " | ".join(fmt_stretch(d) for d in g_dicts),
        "easy_stretches": " | ".join(fmt_stretch(d) for d in e_dicts),
        "longest_gauntlet": longest,
        "gauntlet_weeks_total": g_weeks_total,
        "easy_weeks_total": e_weeks_total,
        "n_gauntlets": len(g_dicts),
        "n_easy": len(e_dicts),
        "_gauntlet_list": g_dicts,
        "_easy_list": e_dicts,
    }


def hardest_4week_window(tw: pd.DataFrame, wt_map: dict[str, float]) -> dict:
    """Return team/week-range with highest average opponent win_total over HARD_WINDOW weeks (no bye in window)."""
    best = None
    for team in teams.ALL_TEAMS:
        rows = tw[tw["team"] == team].sort_values("week")
        opps = [(int(r["week"]), r["opp"]) for _, r in rows.iterrows()]
        for i in range(len(opps) - HARD_WINDOW + 1):
            window = opps[i:i + HARD_WINDOW]
            if any(o is None or not isinstance(o, str) for _, o in window):
                continue
            avg = float(np.mean([wt_map.get(o, np.nan) for _, o in window]))
            if best is None or avg > best["avg_opp_wt"]:
                best = {
                    "team": team,
                    "start_week": window[0][0],
                    "end_week": window[-1][0],
                    "avg_opp_wt": avg,
                    "opponents": ",".join(o for _, o in window),
                }
    return best


def make_chart(tw: pd.DataFrame, summary: pd.DataFrame, top: set[str], bottom: set[str], wt_map: dict[str, float], path):
    weeks = sorted(tw["week"].unique())
    teams_ordered = summary.sort_values(
        ["longest_gauntlet", "gauntlet_weeks_total"], ascending=[False, False]
    )["team"].tolist()

    color_top = "#c0392b"      # red
    color_bottom = "#2980b9"   # blue
    color_mid = "#bdc3c7"      # gray
    color_bye = "#000000"      # black

    fig, ax = plt.subplots(figsize=(14, 10))

    for yi, team in enumerate(teams_ordered):
        row = tw[tw["team"] == team].set_index("week")
        for w in weeks:
            opp = row.loc[w, "opp"] if w in row.index else None
            if opp is None or (isinstance(opp, float) and np.isnan(opp)) or not isinstance(opp, str):
                color = color_bye
                label = "BYE"
            elif opp in top:
                color = color_top
                label = opp
            elif opp in bottom:
                color = color_bottom
                label = opp
            else:
                color = color_mid
                label = opp
            ax.add_patch(plt.Rectangle((w - 0.5, yi - 0.5), 1, 1, facecolor=color, edgecolor="white", linewidth=0.5))
            text_color = "white" if color in (color_top, color_bye, color_bottom) else "black"
            ax.text(w, yi, label, ha="center", va="center", fontsize=6, color=text_color)

    ax.set_xlim(0.5, max(weeks) + 0.5)
    ax.set_ylim(-0.5, len(teams_ordered) - 0.5)
    ax.invert_yaxis()
    ax.set_yticks(range(len(teams_ordered)))
    ax.set_yticklabels(teams_ordered)
    ax.set_xticks(weeks)
    ax.set_xlabel("Week")
    ax.set_ylabel("Team (sorted by longest gauntlet)")
    ax.set_title("2026 Schedule Gauntlets: opponent tier by team-week\n(red = top-10 win total opponent, blue = bottom-10, gray = mid, black = bye)")

    legend_handles = [
        Patch(facecolor=color_top, label="Top-10 opp"),
        Patch(facecolor=color_mid, label="Mid opp"),
        Patch(facecolor=color_bottom, label="Bottom-10 opp"),
        Patch(facecolor=color_bye, label="Bye"),
    ]
    ax.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=4, frameon=False)

    plt.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main():
    schedule = nflverse.load_schedule_2026()
    win_totals = nflverse.load_win_totals_2026()
    if win_totals is None:
        raise SystemExit("win_totals_2026.csv not found")

    top, bottom, wt_map = assign_tiers(win_totals)
    tw = build_team_week_table(schedule)

    summaries = [summarize_team(t, tw, top, bottom) for t in teams.ALL_TEAMS]
    summary_df = pd.DataFrame(summaries)

    # Persist (drop internal raw list columns)
    data_df = summary_df.drop(columns=["_gauntlet_list", "_easy_list"]).copy()
    output.write_data(SLUG, data_df)

    # Chart
    make_chart(tw, summary_df, top, bottom, wt_map, output.chart_path(SLUG))

    # Hardest 4-week window
    hardest = hardest_4week_window(tw, wt_map)

    # Findings
    # Worst gauntlet = team with longest gauntlet (break ties by total gauntlet weeks, then by avg opp wt)
    def worst_gauntlet_team():
        candidates = []
        for s in summaries:
            for g in s["_gauntlet_list"]:
                opps = g["opponents"].split(",")
                avg_wt = float(np.mean([wt_map.get(o, np.nan) for o in opps]))
                candidates.append((s["team"], g, avg_wt))
        if not candidates:
            return None
        # rank by length desc, then avg_wt desc
        candidates.sort(key=lambda x: (x[1]["length"], x[2]), reverse=True)
        return candidates[0]

    def easiest_stretch_team():
        candidates = []
        for s in summaries:
            for e in s["_easy_list"]:
                opps = e["opponents"].split(",")
                avg_wt = float(np.mean([wt_map.get(o, np.nan) for o in opps]))
                candidates.append((s["team"], e, avg_wt))
        if not candidates:
            return None
        # longest, then lowest avg_wt
        candidates.sort(key=lambda x: (x[1]["length"], -x[2]), reverse=True)
        return candidates[0]

    worst = worst_gauntlet_team()
    easiest = easiest_stretch_team()

    # Most fortunate = highest (easy_weeks_total - gauntlet_weeks_total)
    summary_df["fortune"] = summary_df["easy_weeks_total"] - summary_df["gauntlet_weeks_total"]
    fortunate = summary_df.sort_values(["fortune", "easy_weeks_total"], ascending=[False, False]).iloc[0]
    unfortunate = summary_df.sort_values(["fortune", "gauntlet_weeks_total"], ascending=[True, False]).iloc[0]

    lines = ["# 2026 Schedule Gauntlet Report", ""]
    lines.append(f"Tier definitions from Vegas win totals: top-10 (BAL 11.5 down to BUF 10.5) and bottom-10 (CAR 7.5 down to MIA 4.5). A gauntlet/easy stretch = 3+ consecutive weeks against same-tier opponents (byes break the streak).")
    lines.append("")
    if worst:
        team, g, avg_wt = worst
        lines.append(f"- **Worst gauntlet**: {team} faces a {g['length']}-game top-tier slate in Weeks {g['start_week']}-{g['end_week']} ({g['opponents']}), averaging {avg_wt:.2f} opponent win total.")
    if easiest:
        team, e, avg_wt = easiest
        lines.append(f"- **Easiest stretch**: {team} catches a {e['length']}-game bottom-tier run in Weeks {e['start_week']}-{e['end_week']} ({e['opponents']}), averaging {avg_wt:.2f} opponent win total.")
    lines.append(f"- **Most fortunate team**: {fortunate['team']} — {int(fortunate['easy_weeks_total'])} weeks vs bottom-tier opponents and only {int(fortunate['gauntlet_weeks_total'])} vs top-tier (net fortune {int(fortunate['fortune'])}).")
    lines.append(f"- **Least fortunate team**: {unfortunate['team']} — {int(unfortunate['gauntlet_weeks_total'])} weeks vs top-tier and only {int(unfortunate['easy_weeks_total'])} vs bottom-tier (net fortune {int(unfortunate['fortune'])}).")
    if hardest:
        lines.append(f"- **League's hardest 4-week window**: {hardest['team']} Weeks {hardest['start_week']}-{hardest['end_week']} ({hardest['opponents']}), avg opponent win total {hardest['avg_opp_wt']:.2f}.")
    lines.append("")
    n_g = sum(s["n_gauntlets"] for s in summaries)
    n_e = sum(s["n_easy"] for s in summaries)
    lines.append(f"Across the league: {n_g} qualifying gauntlets and {n_e} qualifying easy stretches identified.")

    output.write_findings(SLUG, "\n".join(lines))

    print(f"Wrote artifacts for slug={SLUG}: {len(data_df)} teams")
    print(f"  Worst gauntlet: {worst[0]} W{worst[1]['start_week']}-{worst[1]['end_week']} (len {worst[1]['length']})" if worst else "  No gauntlets")
    print(f"  Easiest stretch: {easiest[0]} W{easiest[1]['start_week']}-{easiest[1]['end_week']} (len {easiest[1]['length']})" if easiest else "  No easies")
    print(f"  Hardest 4wk: {hardest}")


if __name__ == "__main__":
    main()
