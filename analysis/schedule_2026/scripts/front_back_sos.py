"""Front-loaded vs back-loaded Strength of Schedule for 2026.

For each team, compute average opponent win_total across the season and across
splits (H1/H2 and quartiles). Use the H2-H1 swing as a dynasty-trade-deadline
signal:
  - Positive swing  -> schedule gets harder in H2  -> SELL high in H1
  - Negative swing  -> schedule eases in H2        -> BUY low in H1
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "front_back_sos"

# Week split definitions (inclusive on both ends).
H1_WEEKS = range(1, 10)   # 1..9
H2_WEEKS = range(10, 19)  # 10..18
Q1_WEEKS = range(1, 6)    # 1..5
Q2_WEEKS = range(6, 10)   # 6..9
Q3_WEEKS = range(10, 15)  # 10..14
Q4_WEEKS = range(15, 19)  # 15..18

# Thresholds for sell-high / buy-low signal (in win-total points).
SIGNAL_THRESHOLD = 0.5


def build_opponent_frame() -> pd.DataFrame:
    """Long frame: one row per (team, week, opponent, opponent_win_total)."""
    sched = nflverse.load_schedule_2026()
    wt = nflverse.load_win_totals_2026()
    if wt is None:
        raise RuntimeError("win_totals_2026.csv not found")

    wt_map = dict(zip(wt["team"], wt["win_total"]))

    rows = []
    for _, g in sched.iterrows():
        week = int(g["week"])
        away, home = g["away_team"], g["home_team"]
        rows.append({"team": home, "week": week, "opp": away,
                     "opp_win_total": wt_map.get(away, np.nan)})
        rows.append({"team": away, "week": week, "opp": home,
                     "opp_win_total": wt_map.get(home, np.nan)})
    return pd.DataFrame(rows)


def avg_in_weeks(df: pd.DataFrame, weeks) -> float:
    sub = df[df["week"].isin(weeks)]
    if sub.empty:
        return float("nan")
    return float(sub["opp_win_total"].mean())


def classify(swing: float) -> str:
    if swing >= SIGNAL_THRESHOLD:
        return "sell-high candidate"
    if swing <= -SIGNAL_THRESHOLD:
        return "buy-low candidate"
    return "neutral"


def compute_team_table(opp_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for team in teams.ALL_TEAMS:
        td = opp_df[opp_df["team"] == team]
        full = float(td["opp_win_total"].mean())
        h1 = avg_in_weeks(td, H1_WEEKS)
        h2 = avg_in_weeks(td, H2_WEEKS)
        q1 = avg_in_weeks(td, Q1_WEEKS)
        q2 = avg_in_weeks(td, Q2_WEEKS)
        q3 = avg_in_weeks(td, Q3_WEEKS)
        q4 = avg_in_weeks(td, Q4_WEEKS)
        swing = h2 - h1
        rows.append({
            "team": team,
            "full_season_avg": round(full, 3),
            "h1_avg": round(h1, 3),
            "h2_avg": round(h2, 3),
            "swing": round(swing, 3),
            "q1_avg": round(q1, 3),
            "q2_avg": round(q2, 3),
            "q3_avg": round(q3, 3),
            "q4_avg": round(q4, 3),
            "trade_signal": classify(swing),
        })
    df = pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)
    return df


def plot_scatter(df: pd.DataFrame, path) -> None:
    fig, ax = plt.subplots(figsize=(11, 11))

    x = df["h1_avg"].to_numpy()
    y = df["h2_avg"].to_numpy()

    # Color points by trade signal.
    color_map = {
        "sell-high candidate": "#d62728",  # red
        "buy-low candidate": "#2ca02c",    # green
        "neutral": "#7f7f7f",              # gray
    }
    colors = [color_map[s] for s in df["trade_signal"]]
    ax.scatter(x, y, s=70, c=colors, edgecolors="black", linewidths=0.6, zorder=3)

    # Label each team.
    for _, row in df.iterrows():
        ax.annotate(
            row["team"],
            (row["h1_avg"], row["h2_avg"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold",
        )

    # Diagonal y=x reference line spanning the visible range.
    lo = min(x.min(), y.min()) - 0.3
    hi = max(x.max(), y.max()) + 0.3
    ax.plot([lo, hi], [lo, hi], "k--", alpha=0.4, zorder=1, label="H1 = H2 (no swing)")

    # Quadrant guides at the medians.
    x_mid = float(np.median(x))
    y_mid = float(np.median(y))
    ax.axvline(x_mid, color="gray", linestyle=":", alpha=0.3, zorder=1)
    ax.axhline(y_mid, color="gray", linestyle=":", alpha=0.3, zorder=1)

    # Quadrant annotations.
    pad = 0.05
    ax.text(lo + pad, hi - pad,
            "TOP-LEFT\nEasy H1, Hard H2\nSELL-HIGH candidates",
            ha="left", va="top", fontsize=10, fontweight="bold", color="#d62728",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#d62728", alpha=0.85))
    ax.text(hi - pad, lo + pad,
            "BOTTOM-RIGHT\nHard H1, Easy H2\nBUY-LOW candidates",
            ha="right", va="bottom", fontsize=10, fontweight="bold", color="#2ca02c",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#2ca02c", alpha=0.85))
    ax.text(hi - pad, hi - pad,
            "TOP-RIGHT\nHard all year",
            ha="right", va="top", fontsize=9, color="#555",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999", alpha=0.8))
    ax.text(lo + pad, lo + pad,
            "BOTTOM-LEFT\nEasy all year",
            ha="left", va="bottom", fontsize=9, color="#555",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999", alpha=0.8))

    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("H1 SoS — avg opponent win total (weeks 1-9)", fontsize=12)
    ax.set_ylabel("H2 SoS — avg opponent win total (weeks 10-18)", fontsize=12)
    ax.set_title(
        "NFL 2026 Front-loaded vs Back-loaded Schedule\n"
        "(higher opponent win total = tougher schedule)",
        fontsize=13,
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower left", fontsize=9)

    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def build_findings(df: pd.DataFrame) -> str:
    # Highest positive swing = SELL HIGH (gets tougher).
    sell = df.sort_values("swing", ascending=False).head(3)
    # Most negative swing = BUY LOW (gets easier).
    buy = df.sort_values("swing", ascending=True).head(3)

    def fmt_row(r) -> str:
        return (
            f"- **{r['team']}** — swing **{r['swing']:+.2f}** "
            f"(H1 {r['h1_avg']:.2f} -> H2 {r['h2_avg']:.2f})"
        )

    sell_lines = "\n".join(fmt_row(r) for _, r in sell.iterrows())
    buy_lines = "\n".join(fmt_row(r) for _, r in buy.iterrows())

    # Headline numbers for the prose paragraph.
    top_sell = sell.iloc[0]
    top_buy = buy.iloc[0]

    md = f"""# Front-loaded vs Back-loaded SoS — 2026

Average opponent Vegas win total is used as the strength-of-schedule (SoS) proxy.
A positive **swing** (H2 avg minus H1 avg) means the schedule gets harder after
the bye-week stretch; a negative swing means it eases. The dynasty implication
is timing: ride hot starts to **sell high** before the schedule turns, and
**buy low** on teams whose ugly H1 record is partly a schedule artifact.

## Sell-high candidates (largest positive H2 swing)

These teams should outperform in the first half, then fade as the slate
toughens. Look to deal their **win-total beneficiaries** (RB1s, WR1s, breakout
QBs) into a contender by week 8.

{sell_lines}

## Buy-low candidates (largest negative H2 swing)

These teams face a brutal front nine and should look healthier after the bye.
Their young assets are likely to be **discounted** on the back of a slow start —
target them in mid-October trade windows.

{buy_lines}

## Read

The starkest swing belongs to **{top_sell['team']}** at **{top_sell['swing']:+.2f}**
points of opponent win total, going from a cake-walk **{top_sell['h1_avg']:.2f}** H1
to a punishing **{top_sell['h2_avg']:.2f}** H2 — classic dump-and-run timing.
On the flip side, **{top_buy['team']}** swings **{top_buy['swing']:+.2f}**:
opponents averaging **{top_buy['h1_avg']:.2f}** wins early, easing to
**{top_buy['h2_avg']:.2f}** late — the kind of profile where a 2-5 start
masks a viable second-half push.
"""
    return md


def main() -> None:
    opp_df = build_opponent_frame()
    table = compute_team_table(opp_df)
    assert len(table) == 32, f"expected 32 teams, got {len(table)}"

    data_path = output.write_data(SLUG, table)
    chart_p = output.chart_path(SLUG)
    plot_scatter(table, chart_p)
    findings_path = output.write_findings(SLUG, build_findings(table))

    print(f"wrote {data_path}")
    print(f"wrote {chart_p}")
    print(f"wrote {findings_path}")
    print()
    print("=== top 5 sell-high (largest +swing) ===")
    print(table.sort_values("swing", ascending=False).head(5).to_string(index=False))
    print()
    print("=== top 5 buy-low (largest -swing) ===")
    print(table.sort_values("swing", ascending=True).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
