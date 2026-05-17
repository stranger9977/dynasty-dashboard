"""Position-specific Strength of Schedule for 2026 (RB / WR / TE).

Approach:
1. Compute fantasy points (PPR) allowed per game by each defense, by position,
   over 2023-2025 PBP. Weight the seasons by recency (2025=0.5, 2024=0.3, 2023=0.2).
2. Apply 2026 schedule: for each offense, the mean opponent FPA/position across
   its 17 opponents. Convert to a 0-100 percentile (lower = easier matchups).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "position_sos"

SEASONS = [2023, 2024, 2025]
SEASON_WEIGHTS = {2025: 0.5, 2024: 0.3, 2023: 0.2}
POSITIONS = ["RB", "WR", "TE"]


def build_player_position_map() -> dict[str, str]:
    """gsis_id -> position, merged across 2024+2025 rosters (2025 takes precedence)."""
    r24 = nflverse.load_rosters(2024)
    r25 = nflverse.load_rosters(2025)
    # Drop dupes within each season-roster, keep first occurrence
    r24 = r24.dropna(subset=["gsis_id"]).drop_duplicates(subset=["gsis_id"])
    r25 = r25.dropna(subset=["gsis_id"]).drop_duplicates(subset=["gsis_id"])
    m: dict[str, str] = {}
    for _, row in r24.iterrows():
        m[row["gsis_id"]] = row["position"]
    # 2025 overrides 2024
    for _, row in r25.iterrows():
        m[row["gsis_id"]] = row["position"]
    return m


def compute_player_game_points(pbp: pd.DataFrame, pos_map: dict[str, str]) -> pd.DataFrame:
    """Compute PPR points per (player, game, defteam, position) row."""
    # Filter to regular season offensive plays
    df = pbp[pbp["season_type"] == "REG"].copy()

    # Rushing rows: one row per play where rusher_player_id is not null
    rush = df[df["rusher_player_id"].notna() & (df["play_type"] == "run")].copy()
    rush["player_id"] = rush["rusher_player_id"]
    rush["rush_yards"] = rush["rushing_yards"].fillna(0)
    rush["rush_td"] = rush["rush_touchdown"].fillna(0)
    # fumble_lost on a rush play attributed to the rusher (best-effort: only if rusher fumbled).
    # Use fumbled_1_player_id == rusher_player_id to be safe.
    rush["rush_fumble"] = np.where(
        rush["fumbled_1_player_id"].fillna("") == rush["rusher_player_id"].fillna(""),
        rush["fumble_lost"].fillna(0),
        0,
    )
    rush["points"] = (
        0.1 * rush["rush_yards"]
        + 6.0 * rush["rush_td"]
        - 2.0 * rush["rush_fumble"]
    )
    rush_agg = rush.groupby(["player_id", "season", "week", "game_id", "defteam"], as_index=False)["points"].sum()

    # Receiving rows: completed passes with receiver_player_id not null
    rec = df[
        df["receiver_player_id"].notna()
        & (df["play_type"] == "pass")
        & (df["complete_pass"].fillna(0) == 1)
    ].copy()
    rec["player_id"] = rec["receiver_player_id"]
    rec["rec_yards"] = rec["receiving_yards"].fillna(0)
    rec["rec_td"] = rec["pass_touchdown"].fillna(0)
    rec["rec_fumble"] = np.where(
        rec["fumbled_1_player_id"].fillna("") == rec["receiver_player_id"].fillna(""),
        rec["fumble_lost"].fillna(0),
        0,
    )
    rec["points"] = (
        1.0  # reception
        + 0.1 * rec["rec_yards"]
        + 6.0 * rec["rec_td"]
        - 2.0 * rec["rec_fumble"]
    )
    rec_agg = rec.groupby(["player_id", "season", "week", "game_id", "defteam"], as_index=False)["points"].sum()

    # Combine
    combined = pd.concat([rush_agg, rec_agg], ignore_index=True)
    combined = combined.groupby(
        ["player_id", "season", "week", "game_id", "defteam"], as_index=False
    )["points"].sum()

    # Attach position
    combined["position"] = combined["player_id"].map(pos_map)
    combined = combined[combined["position"].isin(POSITIONS)].copy()
    return combined


def compute_fpa_per_position(player_game: pd.DataFrame) -> pd.DataFrame:
    """For each (defteam, season, position): total points allowed and games played.

    Returns long frame with cols: defteam, season, position, fpa_per_game.
    """
    # Total points by defense × season × position × game
    by_game = player_game.groupby(
        ["defteam", "season", "position", "game_id"], as_index=False
    )["points"].sum()
    # Mean per game across the season
    agg = by_game.groupby(["defteam", "season", "position"], as_index=False).agg(
        fpa_total=("points", "sum"),
        games=("game_id", "nunique"),
    )
    agg["fpa_per_game"] = agg["fpa_total"] / agg["games"]
    return agg[["defteam", "season", "position", "fpa_per_game"]]


def weighted_fpa(season_fpa: pd.DataFrame) -> pd.DataFrame:
    """Apply recency weights across seasons. Returns defteam x position -> fpa."""
    season_fpa = season_fpa.copy()
    season_fpa["weight"] = season_fpa["season"].map(SEASON_WEIGHTS)
    # Normalize weights *within* (defteam, position) in case a season is missing for a team
    sum_w = season_fpa.groupby(["defteam", "position"])["weight"].transform("sum")
    season_fpa["weight_norm"] = season_fpa["weight"] / sum_w
    season_fpa["weighted_fpa"] = season_fpa["fpa_per_game"] * season_fpa["weight_norm"]
    out = season_fpa.groupby(["defteam", "position"], as_index=False)["weighted_fpa"].sum()
    out = out.rename(columns={"weighted_fpa": "fpa_per_game"})
    return out


def build_opponent_frame(sched: pd.DataFrame) -> pd.DataFrame:
    """Long frame of (team, week, opp) for the 2026 regular season."""
    rows = []
    for _, g in sched.iterrows():
        if str(g.get("game_type", "REG")) != "REG":
            continue
        week = int(g["week"])
        away, home = g["away_team"], g["home_team"]
        rows.append({"team": home, "week": week, "opp": away})
        rows.append({"team": away, "week": week, "opp": home})
    return pd.DataFrame(rows)


def compute_sos_table(opp_df: pd.DataFrame, fpa: pd.DataFrame) -> pd.DataFrame:
    """For each offense, mean opp FPA across the 17 opponents, by position."""
    fpa_pivot = fpa.pivot(index="defteam", columns="position", values="fpa_per_game")
    fpa_pivot = fpa_pivot.reindex(teams.ALL_TEAMS)

    rows = []
    for team in teams.ALL_TEAMS:
        opps = opp_df[opp_df["team"] == team]["opp"].tolist()
        rb = float(fpa_pivot.loc[opps, "RB"].mean())
        wr = float(fpa_pivot.loc[opps, "WR"].mean())
        te = float(fpa_pivot.loc[opps, "TE"].mean())
        rows.append({
            "team": team,
            "rb_opp_fpa": round(rb, 3),
            "wr_opp_fpa": round(wr, 3),
            "te_opp_fpa": round(te, 3),
            "n_opps": len(opps),
        })
    df = pd.DataFrame(rows)

    # Percentile-rank into 0-100. Higher opp FPA -> easier -> LOWER score
    # (per spec: "Lower score = easier matchups, good for that position").
    # So a team facing the most generous (high FPA) defenses gets a LOW score.
    # rank ascending so the smallest opp FPA -> rank 0 -> score? No — we want
    # easy matchups to map to LOW score. Easy = high opp FPA (defenses give
    # up lots of points). So rank by opp FPA ascending: highest FPA -> high rank.
    # Then we want low score = high FPA. So score = (1 - pct_rank) * 100.
    n = len(df)
    for pos_low in ["rb", "wr", "te"]:
        col = f"{pos_low}_opp_fpa"
        # rank ascending: smallest FPA -> rank 1 (toughest schedule)
        ranks = df[col].rank(method="average", ascending=True)
        # Easy schedule (high FPA) -> high rank. We want easy -> LOW score.
        # So score = (n - rank) / (n - 1) * 100 inverted... use 1-based percentile.
        pct = (ranks - 1) / (n - 1)  # 0 = toughest, 1 = easiest
        score = (1 - pct) * 100  # 0 = easiest, 100 = toughest
        df[f"{pos_low}_sos_score"] = score.round(1)

    return df[[
        "team",
        "rb_sos_score", "wr_sos_score", "te_sos_score",
        "rb_opp_fpa", "wr_opp_fpa", "te_opp_fpa",
    ]]


def plot_heatmap(df: pd.DataFrame, path) -> None:
    """32 teams x 3 positions heatmap of SoS scores."""
    # Order teams by mean SoS score for readability
    df2 = df.copy()
    df2["mean_score"] = df2[["rb_sos_score", "wr_sos_score", "te_sos_score"]].mean(axis=1)
    df2 = df2.sort_values("mean_score", ascending=True).reset_index(drop=True)

    matrix = df2[["rb_sos_score", "wr_sos_score", "te_sos_score"]].to_numpy()
    fig, ax = plt.subplots(figsize=(7, 13))
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=100)

    ax.set_xticks(range(3))
    ax.set_xticklabels(["RB", "WR", "TE"], fontsize=12, fontweight="bold")
    ax.set_yticks(range(len(df2)))
    ax.set_yticklabels(df2["team"].tolist(), fontsize=9)

    # Annotate each cell with the score
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            color = "white" if val < 25 or val > 75 else "black"
            ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                    color=color, fontsize=8)

    ax.set_title(
        "2026 Position SoS — PPR points allowed per game by position\n"
        "(0 = easiest schedule for that position, 100 = toughest)",
        fontsize=11,
    )
    cbar = fig.colorbar(im, ax=ax, shrink=0.5, pad=0.02)
    cbar.set_label("SoS score (lower = easier)", fontsize=10)

    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def build_findings(df: pd.DataFrame) -> str:
    sections = []
    pos_labels = {"rb": "RB", "wr": "WR", "te": "TE"}
    for pos_low, label in pos_labels.items():
        score_col = f"{pos_low}_sos_score"
        fpa_col = f"{pos_low}_opp_fpa"
        # Lower score = easier (best matchups for that position)
        best = df.sort_values(score_col, ascending=True).head(5)
        worst = df.sort_values(score_col, ascending=False).head(5)

        best_lines = "\n".join(
            f"- **{r['team']}** — SoS {r[score_col]:.0f}, opp FPA {r[fpa_col]:.2f}"
            for _, r in best.iterrows()
        )
        worst_lines = "\n".join(
            f"- **{r['team']}** — SoS {r[score_col]:.0f}, opp FPA {r[fpa_col]:.2f}"
            for _, r in worst.iterrows()
        )
        sections.append(
            f"## {label}\n\n"
            f"**Best matchup schedules (easiest for {label}s):**\n{best_lines}\n\n"
            f"**Worst matchup schedules (toughest for {label}s):**\n{worst_lines}"
        )

    md = (
        "# Position SoS — 2026\n\n"
        "Per-position strength of schedule using PPR fantasy points allowed per "
        "game by each defense over 2023-2025 (recency-weighted 50/30/20). For "
        "each 2026 offense, we average the FPA/position of its 17 opponents and "
        "convert to a 0-100 percentile: **lower = easier matchups** for that "
        "position group.\n\n"
        + "\n\n".join(sections)
        + "\n"
    )
    return md


def main() -> None:
    print("loading PBP 2023-2025...")
    pbp = nflverse.load_pbp(SEASONS)
    print(f"  {len(pbp):,} plays")

    print("building player position map...")
    pos_map = build_player_position_map()
    print(f"  {len(pos_map):,} player ids")

    print("computing player-game fantasy points...")
    player_game = compute_player_game_points(pbp, pos_map)
    print(f"  {len(player_game):,} player-game rows")

    print("aggregating FPA/position by defense × season...")
    season_fpa = compute_fpa_per_position(player_game)

    print("applying recency weights...")
    fpa = weighted_fpa(season_fpa)
    print(f"  fpa rows: {len(fpa)} (expect 32*3 = 96)")

    print("loading 2026 schedule...")
    sched = nflverse.load_schedule_2026()
    opp_df = build_opponent_frame(sched)

    print("computing SoS table...")
    table = compute_sos_table(opp_df, fpa)
    assert len(table) == 32, f"expected 32 teams, got {len(table)}"
    # Sanity check: each team should face 17 opponents
    counts = opp_df.groupby("team")["opp"].count()
    assert (counts == 17).all(), f"not all teams have 17 games: {counts[counts != 17]}"

    data_path = output.write_data(SLUG, table)
    chart_p = output.chart_path(SLUG)
    plot_heatmap(table, chart_p)
    findings_path = output.write_findings(SLUG, build_findings(table))

    print(f"wrote {data_path}")
    print(f"wrote {chart_p}")
    print(f"wrote {findings_path}")
    print()
    print("=== sample table (first 8 rows) ===")
    print(table.head(8).to_string(index=False))
    print()
    print("=== easiest RB schedules ===")
    print(table.sort_values("rb_sos_score").head(5).to_string(index=False))
    print()
    print("=== toughest RB schedules ===")
    print(table.sort_values("rb_sos_score", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
