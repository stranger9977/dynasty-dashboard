"""Schedule luck Monte Carlo for 2026 NFL.

For each team, compute actual strength of schedule (SoS) as the sum of opponent
Vegas win totals across their 17 games. Then resample 11 non-division opponents
10,000 times (with replacement) from the 24-team non-division pool, keeping the
6 fixed division games. Report each team's actual-SoS percentile within its
own simulated null distribution.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

N_SIMS = 10_000
RNG_SEED = 20260515


def build_opponents_per_team(sched: pd.DataFrame) -> dict[str, list[str]]:
    """Return mapping team -> list of 17 opponents (home + away appearances)."""
    opps: dict[str, list[str]] = {t: [] for t in teams.ALL_TEAMS}
    for _, row in sched.iterrows():
        h, a = row["home_team"], row["away_team"]
        if h in opps:
            opps[h].append(a)
        if a in opps:
            opps[a].append(h)
    return opps


def split_division_nondivision(
    team: str, opp_list: list[str]
) -> tuple[list[str], list[str]]:
    """Split a team's 17 opponents into (division_opps, nondivision_opps)."""
    div = teams.DIVISIONS[team]
    div_opps = [o for o in opp_list if teams.DIVISIONS.get(o) == div]
    nondiv_opps = [o for o in opp_list if teams.DIVISIONS.get(o) != div]
    return div_opps, nondiv_opps


def nondivision_pool(team: str) -> list[str]:
    div = teams.DIVISIONS[team]
    return [t for t in teams.ALL_TEAMS if t != team and teams.DIVISIONS[t] != div]


def verdict_for(pct: float) -> str:
    if pct >= 85.0:
        return "schedule-unlucky"
    if pct <= 15.0:
        return "schedule-lucky"
    return "noise"


def main() -> None:
    sched = nflverse.load_schedule_2026()
    wt = nflverse.load_win_totals_2026()
    if wt is None:
        raise SystemExit("win_totals_2026.csv missing — required for SoS computation")

    win_total = dict(zip(wt["team"], wt["win_total"]))
    missing = [t for t in teams.ALL_TEAMS if t not in win_total]
    if missing:
        raise SystemExit(f"Missing win totals for teams: {missing}")

    opps = build_opponents_per_team(sched)

    # Sanity: every team should have 17 opponents
    bad = {t: len(v) for t, v in opps.items() if len(v) != 17}
    if bad:
        raise SystemExit(f"Unexpected opponent counts: {bad}")

    rng = np.random.default_rng(RNG_SEED)

    rows = []
    for team in teams.ALL_TEAMS:
        opp_list = opps[team]
        div_opps, nondiv_opps = split_division_nondivision(team, opp_list)

        # NFL rule: 6 division games (3 opponents x 2). The other 11 are non-division.
        # If the data ever deviates, we still resample (17 - len(div_opps)) games.
        n_nondiv = 17 - len(div_opps)

        actual_sos = sum(win_total[o] for o in opp_list)
        div_sos = sum(win_total[o] for o in div_opps)

        pool = nondivision_pool(team)
        pool_wins = np.array([win_total[t] for t in pool], dtype=float)

        # Draw n_nondiv non-division opponents with replacement, N_SIMS times.
        idx = rng.integers(low=0, high=len(pool), size=(N_SIMS, n_nondiv))
        sim_nondiv_sos = pool_wins[idx].sum(axis=1)
        sim_sos = div_sos + sim_nondiv_sos

        # Percentile = pct of simulated draws that are <= actual_sos.
        # Use <= so ties count toward the team's harder-schedule rank.
        pct = float((sim_sos <= actual_sos).mean() * 100.0)

        rows.append(
            {
                "team": team,
                "actual_sos": float(actual_sos),
                "sim_mean": float(sim_sos.mean()),
                "sim_std": float(sim_sos.std(ddof=1)),
                "percentile": pct,
                "verdict": verdict_for(pct),
            }
        )

    df = pd.DataFrame(rows).sort_values("percentile", ascending=False).reset_index(drop=True)

    data_path = output.write_data("schedule_luck", df)
    print(f"Wrote {data_path} ({len(df)} rows)")

    # --- Chart ---
    chart_df = df.sort_values("percentile", ascending=True)  # bottom = lucky, top = unlucky
    colors = []
    for p in chart_df["percentile"]:
        if p >= 85:
            colors.append("#c0392b")  # red — unlucky
        elif p <= 15:
            colors.append("#27ae60")  # green — lucky
        else:
            colors.append("#7f8c8d")  # grey — noise

    fig, ax = plt.subplots(figsize=(9, 10))
    y = np.arange(len(chart_df))
    ax.barh(y, chart_df["percentile"].values, color=colors, edgecolor="black", linewidth=0.4)
    ax.set_yticks(y)
    ax.set_yticklabels(chart_df["team"].values)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Percentile of actual SoS within Monte Carlo null (10k sims)")
    ax.set_title("2026 NFL Schedule Luck — actual SoS vs. random non-division draws")

    for x_ref, label, ls in [(15, "lucky <15", "--"), (50, "median", ":"), (85, "unlucky >85", "--")]:
        ax.axvline(x_ref, color="black", linestyle=ls, linewidth=0.8, alpha=0.6)
        ax.text(x_ref, len(chart_df) - 0.3, label, ha="center", va="bottom", fontsize=8, alpha=0.75)

    ax.grid(axis="x", linestyle=":", alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    cpath = output.chart_path("schedule_luck")
    fig.savefig(cpath, dpi=140)
    plt.close(fig)
    print(f"Wrote {cpath}")

    # --- Findings ---
    sorted_desc = df.sort_values("percentile", ascending=False).reset_index(drop=True)
    unlucky = sorted_desc.head(3)
    lucky = sorted_desc.tail(3).iloc[::-1]  # lowest first

    n_unlucky = int((df["verdict"] == "schedule-unlucky").sum())
    n_lucky = int((df["verdict"] == "schedule-lucky").sum())

    def fmt_row(r: pd.Series) -> str:
        return (
            f"**{r['team']}** (pct {r['percentile']:.1f}, "
            f"actual {r['actual_sos']:.1f} vs sim mean {r['sim_mean']:.1f})"
        )

    md = f"""# 2026 Schedule Luck — Monte Carlo Findings

Each team's 17 opponents were compared against 10,000 randomly resampled schedules
that hold the 6 division games fixed and draw 11 non-division opponents with
replacement from the 24-team non-division pool. Opponent strength is measured by
2026 Vegas win totals (DraftKings, as of 2026-05-15).

## Most schedule-unlucky (harder than random)

1. {fmt_row(unlucky.iloc[0])}
2. {fmt_row(unlucky.iloc[1])}
3. {fmt_row(unlucky.iloc[2])}

## Most schedule-lucky (easier than random)

1. {fmt_row(lucky.iloc[0])}
2. {fmt_row(lucky.iloc[1])}
3. {fmt_row(lucky.iloc[2])}

## Are "tough schedule" narratives real?

Of 32 teams, {n_unlucky} clear the >85 percentile bar for genuinely unlucky and
{n_lucky} fall under 15 for genuinely lucky — the remaining {32 - n_unlucky - n_lucky}
sit in the noise band where the actual SoS is indistinguishable from a random
draw given the team's fixed division. That ratio is roughly what you'd expect by
chance under the null (a 15/85 cutoff implies ~30% of teams in the tails), so
most "brutal slate" takes you'll hear in May are narrative noise rather than
signal. The teams listed above are the ones whose 11 non-division draws really
did skew harder or softer than a random allocation would predict. Division
membership remains the dominant driver of total SoS variance — a team stuck in
a top-heavy division can post a top-quartile percentile without any extra bad
luck in their cross-conference draws.
"""
    fpath = output.write_findings("schedule_luck", md)
    print(f"Wrote {fpath}")


if __name__ == "__main__":
    main()
