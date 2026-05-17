"""Fantasy playoffs (weeks 14-16) Position Strength of Schedule for 2026.

For each 2026 team, compute mean PPR fantasy points allowed per game (FPA) by
their weeks 14, 15, 16 opponents at RB, WR, TE. Recency-weighted from 2023-2025
regular season PBP. This is the most dynasty-actionable schedule artifact:
those are the standard fantasy playoff weeks.

PPR per player-play:
    rush_yds*0.1 + rush_td*6 + rec*1 + rec_yds*0.1 + rec_td*6 - fumble_lost*2
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "ff_playoffs_sos"

PLAYOFF_WEEKS = [14, 15, 16]
POSITIONS = ["RB", "WR", "TE"]
SEASON_WEIGHTS = {2025: 0.50, 2024: 0.30, 2023: 0.20}


# ---------------------------------------------------------------------------
# Position map (gsis_id -> position) from 2024 + 2025 rosters
# ---------------------------------------------------------------------------
def build_position_map() -> dict[str, str]:
    """gsis_id -> RB/WR/TE. 2025 wins ties (latest known role)."""
    pos_map: dict[str, str] = {}
    for season in (2024, 2025):
        r = nflverse.load_rosters(season)
        r = r.dropna(subset=["gsis_id", "position"])
        r = r[r["position"].isin(POSITIONS)]
        # Iterate so 2025 overwrites 2024.
        for gid, pos in zip(r["gsis_id"], r["position"]):
            pos_map[gid] = pos
    return pos_map


# ---------------------------------------------------------------------------
# Fantasy-points-allowed per game by defense, per season, per position.
# ---------------------------------------------------------------------------
def compute_fpa_by_season(pbp: pd.DataFrame, pos_map: dict[str, str]) -> pd.DataFrame:
    """Return one row per (season, defteam, position) with mean PPR-FPA per game."""
    # Regular season only.
    pbp = pbp[pbp["season_type"] == "REG"].copy()

    # ---- Rushing fantasy points per play (attributed to rusher) ----
    rush = pbp[
        (pbp["play_type"] == "run")
        & pbp["rusher_player_id"].notna()
        & pbp["defteam"].notna()
    ][
        [
            "season",
            "game_id",
            "defteam",
            "rusher_player_id",
            "rushing_yards",
            "rush_touchdown",
            "fumble_lost",
        ]
    ].copy()
    rush = rush.rename(columns={"rusher_player_id": "player_id"})
    rush["rushing_yards"] = rush["rushing_yards"].fillna(0.0)
    rush["rush_touchdown"] = rush["rush_touchdown"].fillna(0.0)
    rush["fumble_lost"] = rush["fumble_lost"].fillna(0.0)
    rush["fpts"] = (
        rush["rushing_yards"] * 0.1
        + rush["rush_touchdown"] * 6.0
        - rush["fumble_lost"] * 2.0
    )

    # ---- Receiving fantasy points per play (attributed to receiver, completions only) ----
    rec = pbp[
        (pbp["play_type"] == "pass")
        & (pbp["complete_pass"] == 1)
        & pbp["receiver_player_id"].notna()
        & pbp["defteam"].notna()
    ][
        [
            "season",
            "game_id",
            "defteam",
            "receiver_player_id",
            "receiving_yards",
            "pass_touchdown",
            "fumble_lost",
        ]
    ].copy()
    rec = rec.rename(
        columns={"receiver_player_id": "player_id", "pass_touchdown": "rec_td"}
    )
    rec["receiving_yards"] = rec["receiving_yards"].fillna(0.0)
    rec["rec_td"] = rec["rec_td"].fillna(0.0)
    rec["fumble_lost"] = rec["fumble_lost"].fillna(0.0)
    rec["fpts"] = (
        1.0  # reception
        + rec["receiving_yards"] * 0.1
        + rec["rec_td"] * 6.0
        - rec["fumble_lost"] * 2.0
    )

    plays = pd.concat(
        [
            rush[["season", "game_id", "defteam", "player_id", "fpts"]],
            rec[["season", "game_id", "defteam", "player_id", "fpts"]],
        ],
        ignore_index=True,
    )

    # Attach position via roster map. Drop plays with unknown position
    # (these are usually QBs scrambling — irrelevant to RB/WR/TE FPA).
    plays["position"] = plays["player_id"].map(pos_map)
    plays = plays[plays["position"].isin(POSITIONS)]

    # Sum fpts per (season, game, defense, position) across all opposing players.
    per_game = (
        plays.groupby(["season", "game_id", "defteam", "position"], as_index=False)[
            "fpts"
        ]
        .sum()
    )

    # Mean fpts allowed per game by defense in that season at that position.
    season_fpa = (
        per_game.groupby(["season", "defteam", "position"], as_index=False)["fpts"]
        .mean()
        .rename(columns={"fpts": "fpa_per_game"})
    )
    return season_fpa


def blend_recency(season_fpa: pd.DataFrame) -> pd.DataFrame:
    """Collapse 2023/2024/2025 into a single recency-weighted FPA per (team, pos)."""
    # Normalize team abbreviations to schedule convention. nflverse uses
    # 'LA' for the Rams (matches teams.ALL_TEAMS), but historical data may
    # contain 'STL'/'OAK'/'SD'. Map those if they appear.
    rename = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
    season_fpa = season_fpa.copy()
    season_fpa["defteam"] = season_fpa["defteam"].replace(rename)

    # Pivot to one row per (team, position).
    out_rows = []
    for (team, pos), grp in season_fpa.groupby(["defteam", "position"]):
        # weighted mean across whatever seasons are present
        wsum = 0.0
        vsum = 0.0
        for _, r in grp.iterrows():
            w = SEASON_WEIGHTS.get(int(r["season"]), 0.0)
            if w > 0:
                wsum += w
                vsum += w * float(r["fpa_per_game"])
        if wsum == 0:
            continue
        out_rows.append({
            "defteam": team,
            "position": pos,
            "fpa_blended": vsum / wsum,
        })
    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# Opponents in playoff window
# ---------------------------------------------------------------------------
def playoff_opponents() -> pd.DataFrame:
    """One row per team with (w14_opp, w15_opp, w16_opp) and games_count."""
    sched = nflverse.load_schedule_2026()
    sched = sched[sched["week"].isin(PLAYOFF_WEEKS)].copy()

    # Per (team, week) -> opp.
    rows = []
    for _, g in sched.iterrows():
        week = int(g["week"])
        rows.append({"team": g["home_team"], "week": week, "opp": g["away_team"]})
        rows.append({"team": g["away_team"], "week": week, "opp": g["home_team"]})
    long = pd.DataFrame(rows)

    out = []
    for team in teams.ALL_TEAMS:
        td = long[long["team"] == team]
        wk_to_opp = dict(zip(td["week"].astype(int), td["opp"]))
        out.append({
            "team": team,
            "w14_opp": wk_to_opp.get(14, None),
            "w15_opp": wk_to_opp.get(15, None),
            "w16_opp": wk_to_opp.get(16, None),
            "playoff_games_count": int(td["week"].nunique()),
        })
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Build team x position SoS table
# ---------------------------------------------------------------------------
def build_team_table(blended: pd.DataFrame, opp_df: pd.DataFrame) -> pd.DataFrame:
    """Combine opponent FPA into team-level mean per position + 0-100 score."""
    # Lookups: (team, pos) -> blended FPA
    fpa_lookup: dict[tuple[str, str], float] = {
        (r["defteam"], r["position"]): float(r["fpa_blended"])
        for _, r in blended.iterrows()
    }

    rows = []
    for _, r in opp_df.iterrows():
        team = r["team"]
        opps = [o for o in (r["w14_opp"], r["w15_opp"], r["w16_opp"]) if o]
        row = {
            "team": team,
            "playoff_games_count": int(r["playoff_games_count"]),
            "w14_opp": r["w14_opp"],
            "w15_opp": r["w15_opp"],
            "w16_opp": r["w16_opp"],
        }
        for pos in POSITIONS:
            vals = [fpa_lookup.get((o, pos), np.nan) for o in opps]
            vals = [v for v in vals if not (v is None or np.isnan(v))]
            row[f"{pos.lower()}_opp_fpa"] = float(np.mean(vals)) if vals else np.nan
        rows.append(row)

    df = pd.DataFrame(rows)

    # Convert FPA -> 0-100 per position. Lower opp_fpa = easier matchup -> lower score.
    # We map min(fpa) -> 0 and max(fpa) -> 100.
    for pos in POSITIONS:
        col = f"{pos.lower()}_opp_fpa"
        s_col = f"{pos.lower()}_sos_score"
        lo = df[col].min()
        hi = df[col].max()
        if hi - lo > 0:
            df[s_col] = (df[col] - lo) / (hi - lo) * 100.0
        else:
            df[s_col] = 50.0

    # League-winner aggregate: average of the three SoS scores (lower = better matchups).
    df["lw_score"] = df[[f"{p.lower()}_sos_score" for p in POSITIONS]].mean(axis=1)

    # Round for display.
    for pos in POSITIONS:
        df[f"{pos.lower()}_opp_fpa"] = df[f"{pos.lower()}_opp_fpa"].round(2)
        df[f"{pos.lower()}_sos_score"] = df[f"{pos.lower()}_sos_score"].round(1)
    df["lw_score"] = df["lw_score"].round(2)

    # Final column order matches spec.
    out_cols = [
        "team",
        "playoff_games_count",
        "rb_sos_score", "wr_sos_score", "te_sos_score",
        "rb_opp_fpa", "wr_opp_fpa", "te_opp_fpa",
        "w14_opp", "w15_opp", "w16_opp",
        "lw_score",
    ]
    return df[out_cols].sort_values("lw_score", ascending=True).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Chart: heatmap (32 teams x 3 positions)
# ---------------------------------------------------------------------------
def plot_heatmap(df: pd.DataFrame, path) -> None:
    # Sort by aggregate league-winner score (lowest = easiest playoff slate first).
    d = df.sort_values("lw_score", ascending=True).reset_index(drop=True)

    matrix = d[["rb_sos_score", "wr_sos_score", "te_sos_score"]].to_numpy()
    teams_axis = d["team"].tolist()
    pos_axis = ["RB", "WR", "TE"]

    fig, ax = plt.subplots(figsize=(7, 12))
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=100)

    ax.set_xticks(range(len(pos_axis)))
    ax.set_xticklabels(pos_axis, fontsize=11)
    ax.set_yticks(range(len(teams_axis)))
    ax.set_yticklabels(teams_axis, fontsize=9)

    # Annotate cells with the numeric score.
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            ax.text(
                j, i, f"{val:.0f}",
                ha="center", va="center",
                fontsize=8,
                color="white" if val < 30 or val > 70 else "black",
            )

    cbar = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label("SoS score (0 = easiest, 100 = hardest)", fontsize=10)

    ax.set_title(
        "2026 Fantasy Playoffs Position SoS — Weeks 14-16\n"
        "(sorted top = best aggregate league-winner matchup)",
        fontsize=12,
    )
    ax.set_xlabel("Position room", fontsize=11)
    ax.set_ylabel("Team (sorted by avg score; lower is better)", fontsize=11)

    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
def _opps_str(r: pd.Series) -> str:
    parts = []
    for w, col in [(14, "w14_opp"), (15, "w15_opp"), (16, "w16_opp")]:
        v = r[col]
        if v is None or (isinstance(v, float) and np.isnan(v)):
            parts.append(f"W{w}: BYE")
        else:
            parts.append(f"W{w}: {v}")
    return ", ".join(parts)


def build_findings(df: pd.DataFrame) -> str:
    # Per-position best 3 (lowest score) and worst 3 (highest score).
    sections = {}
    for pos in POSITIONS:
        col = f"{pos.lower()}_sos_score"
        fpa = f"{pos.lower()}_opp_fpa"
        best = df.sort_values(col, ascending=True).head(3)
        worst = df.sort_values(col, ascending=False).head(3)
        sections[pos] = (best, worst, col, fpa)

    bye_teams = df[df["playoff_games_count"] < 3]

    def fmt(r, col, fpa) -> str:
        return (
            f"- **{r['team']} {pos_lc}** — score **{r[col]:.0f}** "
            f"(opp FPA {r[fpa]:.1f}); {_opps_str(r)}"
        )

    md_parts: list[str] = []
    md_parts.append("# Fantasy Playoffs Position SoS — Weeks 14-16, 2026\n")
    md_parts.append(
        "Recency-weighted (2025=50%, 2024=30%, 2023=20%) PPR fantasy points "
        "allowed per game by each defense at RB/WR/TE, averaged across each "
        "team's W14-16 opponents. 0 = easiest, 100 = toughest. This is the "
        "matchup window that decides leagues.\n"
    )

    md_parts.append("## League-winner rooms (best playoff matchups)\n")
    for pos in POSITIONS:
        best, _, col, fpa = sections[pos]
        pos_lc = pos
        lines = [fmt(r, col, fpa) for _, r in best.iterrows()]
        md_parts.append(f"### {pos}\n" + "\n".join(lines) + "\n")

    md_parts.append("## League-loser rooms (worst playoff matchups)\n")
    for pos in POSITIONS:
        _, worst, col, fpa = sections[pos]
        pos_lc = pos
        lines = [fmt(r, col, fpa) for _, r in worst.iterrows()]
        md_parts.append(f"### {pos}\n" + "\n".join(lines) + "\n")

    if not bye_teams.empty:
        bye_lines = []
        for _, r in bye_teams.iterrows():
            bye_lines.append(
                f"- **{r['team']}** — only {int(r['playoff_games_count'])} games in W14-16 "
                f"({_opps_str(r)}). Dynasty red flag: their skill players miss a fantasy-playoff week."
            )
        md_parts.append("## Bye-week landmines (W14-16 byes)\n" + "\n".join(bye_lines) + "\n")
    else:
        md_parts.append(
            "## Bye-week landmines\n\n"
            "No team has a bye in weeks 14-16 this year — every fantasy "
            "starter is on the field for all three playoff weeks.\n"
        )

    # Top aggregate league-winners / losers.
    agg_best = df.sort_values("lw_score", ascending=True).head(3)
    agg_worst = df.sort_values("lw_score", ascending=False).head(3)
    md_parts.append("## Aggregate (all three positions blended)\n")
    md_parts.append("**Easiest overall fantasy-playoff slate:**")
    for _, r in agg_best.iterrows():
        md_parts.append(
            f"- {r['team']} (avg score {r['lw_score']:.1f}; {_opps_str(r)})"
        )
    md_parts.append("\n**Toughest overall fantasy-playoff slate:**")
    for _, r in agg_worst.iterrows():
        md_parts.append(
            f"- {r['team']} (avg score {r['lw_score']:.1f}; {_opps_str(r)})"
        )

    return "\n".join(md_parts) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    print("loading PBP 2023-2025...")
    pbp = nflverse.load_pbp(seasons=[2023, 2024, 2025])
    print(f"  pbp rows: {len(pbp):,}")

    print("building position map...")
    pos_map = build_position_map()
    print(f"  player position map size: {len(pos_map):,}")

    print("computing per-season FPA...")
    season_fpa = compute_fpa_by_season(pbp, pos_map)
    print(f"  season-team-position rows: {len(season_fpa)}")

    print("blending recency...")
    blended = blend_recency(season_fpa)
    print(f"  blended rows: {len(blended)} (expect ~96)")

    print("getting playoff opponents...")
    opp_df = playoff_opponents()
    print(f"  team-opp rows: {len(opp_df)}")

    print("building team table...")
    table = build_team_table(blended, opp_df)
    assert len(table) == 32, f"expected 32 teams, got {len(table)}"

    # Drop the helper lw_score column from the persisted parquet to match the spec schema,
    # but keep it in memory for the chart + findings.
    schema_cols = [
        "team", "playoff_games_count",
        "rb_sos_score", "wr_sos_score", "te_sos_score",
        "rb_opp_fpa", "wr_opp_fpa", "te_opp_fpa",
        "w14_opp", "w15_opp", "w16_opp",
    ]
    data_path = output.write_data(SLUG, table[schema_cols])
    chart_p = output.chart_path(SLUG)
    plot_heatmap(table, chart_p)
    findings_path = output.write_findings(SLUG, build_findings(table))

    print(f"wrote {data_path}")
    print(f"wrote {chart_p}")
    print(f"wrote {findings_path}")
    print()
    print("=== top 5 easiest aggregate playoff slates ===")
    print(
        table.sort_values("lw_score", ascending=True)
        .head(5)
        .to_string(index=False)
    )
    print()
    print("=== top 5 hardest aggregate playoff slates ===")
    print(
        table.sort_values("lw_score", ascending=False)
        .head(5)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
