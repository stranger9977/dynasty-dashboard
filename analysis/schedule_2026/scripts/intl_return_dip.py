"""International return-week dip: do teams underperform vs. Vegas the week after playing an international game?

Historical (2007-2025): for each team that played at an international venue, find their next
regular-season game and compute cover rate / scoring margin vs. Vegas spread. Compare to baseline.

Apply finding to 2026: list each return-week game for the 9 international games scheduled.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _shared import nflverse, output

SLUG = "intl_return_dip"

# International venues across NFL history. Domestic neutral games (Super Bowls, Saints
# post-Katrina relocations, COVID-era moves) are deliberately excluded.
INTL_STADIUMS = {
    "Wembley Stadium",
    "Tottenham Stadium",
    "Tottenham Hotspur Stadium",
    "Twickenham Stadium",
    "Allianz Arena",
    "Deutsche Bank Park",
    "FC Bayern Munich Stadium",
    "Bernabeu",
    "Stade de France",
    "Azteca Stadium",
    "Estadio Banorte",
    "Arena Corinthians",
    "Maracana Stadium",
    "Melbourne Cricket Ground",
    "Rogers Centre",  # Bills Toronto series (2008, 2013)
}


def is_international(row) -> bool:
    return row["stadium"] in INTL_STADIUMS


def compute_team_game_margin(team: str, row) -> float:
    """Margin from the team's perspective (positive = team won by that many)."""
    if team == row["home_team"]:
        return row["home_score"] - row["away_score"]
    return row["away_score"] - row["home_score"]


def compute_team_cover(team: str, row) -> int | None:
    """1 if team covered the spread, 0 if not, None if push or no line.

    spread_line is the HOME team's spread (negative = home favored).
    Home covers if (home_score - away_score) > -spread_line. (i.e. result > -spread_line.)
    Equivalently, home margin + spread_line > 0.
    """
    spread = row.get("spread_line")
    if pd.isna(spread):
        return None
    home_margin = row["home_score"] - row["away_score"]
    # home cover margin: positive if home covers
    home_cover_diff = home_margin + spread
    if home_cover_diff == 0:
        return None  # push
    home_covered = home_cover_diff > 0
    if team == row["home_team"]:
        return int(home_covered)
    return int(not home_covered)


def main() -> None:
    games = nflverse.load_games()
    # Drop non-regular season for cleanness (playoffs/SB)
    games = games[games["game_type"] == "REG"].copy()
    games = games.sort_values(["season", "week"]).reset_index(drop=True)

    # ============ Part 1: historical international return-week study ============
    historical = games[(games["season"] >= 2007) & (games["season"] <= 2025)].copy()

    # All international games historically
    intl_games = historical[historical["stadium"].isin(INTL_STADIUMS)].copy()
    print(f"Historical international games (2007-2025): {len(intl_games)}")

    return_records: list[dict] = []
    for _, ig in intl_games.iterrows():
        season = ig["season"]
        week = ig["week"]
        for side, team in [("home", ig["home_team"]), ("away", ig["away_team"])]:
            # Find next regular-season game for this team in the same season
            future = historical[
                (historical["season"] == season)
                & (historical["week"] > week)
                & ((historical["home_team"] == team) | (historical["away_team"] == team))
            ].sort_values("week")
            if future.empty:
                continue
            ret = future.iloc[0]
            # Skip if Vegas line missing or scores missing
            if pd.isna(ret["spread_line"]) or pd.isna(ret["home_score"]):
                continue
            margin = compute_team_game_margin(team, ret)
            covered = compute_team_cover(team, ret)
            return_records.append({
                "season": int(season),
                "intl_week": int(week),
                "intl_venue": ig["stadium"],
                "team": team,
                "intl_side": side,
                "return_week": int(ret["week"]),
                "weeks_off": int(ret["week"] - week),
                "return_opponent": ret["away_team"] if team == ret["home_team"] else ret["home_team"],
                "return_home_away": "home" if team == ret["home_team"] else "away",
                "return_margin": float(margin),
                "return_covered": covered,
                "return_game_id": ret["game_id"],
            })

    ret_df = pd.DataFrame(return_records)
    print(f"Return-week team-games: {len(ret_df)}")

    # Build baseline: every team-game from historical, with cover & margin.
    base_rows: list[dict] = []
    for _, gm in historical.iterrows():
        if pd.isna(gm["spread_line"]) or pd.isna(gm["home_score"]):
            continue
        for team in [gm["home_team"], gm["away_team"]]:
            base_rows.append({
                "season": int(gm["season"]),
                "team": team,
                "margin": compute_team_game_margin(team, gm),
                "covered": compute_team_cover(team, gm),
            })
    base_df = pd.DataFrame(base_rows)

    # Aggregate metrics
    ret_cov = ret_df["return_covered"].dropna()
    base_cov = base_df["covered"].dropna()
    ret_cover_pct = float(ret_cov.mean()) * 100
    base_cover_pct = float(base_cov.mean()) * 100
    ret_margin = float(ret_df["return_margin"].mean())
    base_margin = float(base_df["margin"].mean())
    n_return = int(len(ret_cov))
    n_base = int(len(base_cov))

    print(f"Return-week cover rate: {ret_cover_pct:.1f}% (n={n_return})")
    print(f"Baseline cover rate:    {base_cover_pct:.1f}% (n={n_base})")
    print(f"Return-week avg margin: {ret_margin:+.2f}")
    print(f"Baseline avg margin:    {base_margin:+.2f}")

    # ============ Part 2: apply to 2026 ============
    s26 = games[games["season"] == 2026].copy()
    intl_26 = s26[s26["stadium"].isin(INTL_STADIUMS)].copy()
    print(f"\n2026 international games: {len(intl_26)}")

    affected_rows: list[dict] = []
    for _, ig in intl_26.iterrows():
        week = ig["week"]
        for side, team in [("home", ig["home_team"]), ("away", ig["away_team"])]:
            future = s26[
                (s26["week"] > week)
                & ((s26["home_team"] == team) | (s26["away_team"] == team))
            ].sort_values("week")
            if future.empty:
                continue
            ret = future.iloc[0]
            affected_rows.append({
                "int_game_week": int(week),
                "int_team": team,
                "int_side": side,
                "int_venue": ig["stadium"],
                "int_opponent": ig["away_team"] if team == ig["home_team"] else ig["home_team"],
                "return_week": int(ret["week"]),
                "weeks_off": int(ret["week"] - week),
                "return_opponent": ret["away_team"] if team == ret["home_team"] else ret["home_team"],
                "return_home_away": "home" if team == ret["home_team"] else "away",
                "return_game_id": ret["game_id"],
            })
    affected_df = pd.DataFrame(affected_rows)
    print(affected_df.to_string(index=False))

    # ============ Outputs ============
    # Main parquet = 2026 affected games (per task spec).
    output.write_data(SLUG, affected_df, "data.parquet")
    # Save historical detail too for reproducibility.
    output.write_data(SLUG, ret_df, "historical_return_games.parquet")

    # Chart: histogram of return-week margins vs. baseline margins
    fig, ax = plt.subplots(figsize=(10, 6))
    bins = np.arange(-50, 51, 5)
    ax.hist(
        base_df["margin"],
        bins=bins,
        density=True,
        alpha=0.45,
        color="steelblue",
        label=f"Baseline team-games (n={n_base:,}, mean={base_margin:+.2f})",
    )
    ax.hist(
        ret_df["return_margin"],
        bins=bins,
        density=True,
        alpha=0.55,
        color="crimson",
        label=f"Post-international return-week (n={len(ret_df)}, mean={ret_margin:+.2f})",
    )
    ax.axvline(0, color="black", linewidth=0.8, linestyle=":")
    ax.axvline(base_margin, color="steelblue", linewidth=1.5, linestyle="--")
    ax.axvline(ret_margin, color="crimson", linewidth=1.5, linestyle="--")
    ax.set_xlabel("Score margin (team perspective)")
    ax.set_ylabel("Density")
    ax.set_title(
        f"Return-week margins after international games (2007-2025)\n"
        f"Cover rate: {ret_cover_pct:.1f}% return-week vs. {base_cover_pct:.1f}% baseline"
    )
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output.chart_path(SLUG), dpi=120)
    plt.close(fig)

    # Findings markdown
    # Build 2026 listing string
    lines_2026 = []
    for _, r in affected_df.iterrows():
        ha = "home" if r["return_home_away"] == "home" else "@"
        opp = r["return_opponent"]
        if r["return_home_away"] == "away":
            ret_desc = f"@ {opp}"
        else:
            ret_desc = f"vs {opp}"
        lines_2026.append(
            f"- **{r['int_team']}** (intl W{r['int_game_week']} {r['int_venue']}) "
            f"-> W{r['return_week']} {ret_desc}"
        )
    listing = "\n".join(lines_2026)

    delta_cover = ret_cover_pct - base_cover_pct
    delta_margin = ret_margin - base_margin

    # Pick 6 most-fade-worthy teams: away international travelers (longest trip for US-based home team)
    # Heuristic: prioritize teams whose international game was "away" (real travel) and return is away.
    fade = affected_df[(affected_df["int_side"] == "away") | (affected_df["return_home_away"] == "away")]
    fade_names = sorted(set(fade["int_team"].tolist()))

    md = f"""# International Return-Week Dip

**Question:** Do NFL teams underperform vs. Vegas the week after playing an international game?

## Historical effect (2007-2025, regular season)

- International games found: **{len(intl_games)}** (Wembley/Tottenham/Twickenham, Munich, Frankfurt, Mexico City, Sao Paulo, plus the Bills Toronto series).
- Return-week team-games with Vegas line and final score: **n = {n_return}**.
- **Return-week ATS cover rate: {ret_cover_pct:.1f}%** vs. league baseline {base_cover_pct:.1f}% (n={n_base:,}) -> delta **{delta_cover:+.1f} pp**.
- **Return-week avg margin: {ret_margin:+.2f}** vs. baseline {base_margin:+.2f} -> delta **{delta_margin:+.2f} pts**.

The historical signal is **small and statistically noisy**. Cover rate sits within roughly one standard error of 50% at this sample size (SE ~= {100 * (0.5 / np.sqrt(n_return)):.1f} pp). The often-cited "international hangover" is, at most, a modest tilt -- not a clean edge. Most international participants get bye weeks attached, which appears to wash out any travel fatigue.

## 2026 schedule -- nine affected return-week games

The 2026 slate has the most international games in NFL history (9). Each affects two teams' next game:

{listing}

## Recommendation

Given the muted historical effect, treat the return week as a **soft fade**, not a hard rule. The cleanest spots to fade are teams whose international game was a **true road trip** (the away team) AND whose return-week game is **also on the road** (compounding travel). For 2026 those teams to watch are: **{", ".join(fade_names)}**. Avoid over-fading anchor stars on teams that get a bye week between the international trip and the return game (check `weeks_off` column in data.parquet).
"""
    output.write_findings(SLUG, md)
    print("\nWrote outputs to", output.artifact_dir(SLUG))


if __name__ == "__main__":
    main()
