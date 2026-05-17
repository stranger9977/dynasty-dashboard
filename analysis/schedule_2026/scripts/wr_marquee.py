"""WR schedule strength + marquee WR-vs-CB matchups for 2026.

Reuses:
- analysis/schedule_2026/output/cb_wr_matchup/data.parquet → team CB unit scores
- data/merged.parquet → WR quality (blended_value 0-100 from FC/KTC/LR)
- _shared.nflverse → 2026 schedule
"""
from __future__ import annotations
import sys
sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')

import matplotlib.pyplot as plt
import pandas as pd

from _shared import nflverse, output

TEAM_FIX = {"GBP": "GB", "KCC": "KC", "LVR": "LV", "NOS": "NO",
            "SFO": "SF", "TBB": "TB", "LAR": "LA"}


def load_wrs() -> pd.DataFrame:
    df = pd.read_parquet("/Users/nick/projects/dynasty-dashboard/data/merged.parquet")
    wrs = df[(df["position"] == "WR") & (df["team"] != "FA")].copy()
    wrs["team"] = wrs["team"].replace(TEAM_FIX)
    return wrs[["name", "team", "blended_value", "fc_pos_rank", "ktc_pos_rank", "age"]]


def main() -> None:
    slug = "cb_wr_matchup"
    schedule = nflverse.load_schedule_2026()
    cb_units = pd.read_parquet(
        "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/output/cb_wr_matchup/data.parquet"
    )[["team", "unit_score"]].rename(columns={"unit_score": "cb_unit"})

    wrs = load_wrs()

    # ────────────────────────  Chart 1: WR Schedule Strength  ────────────────────────
    # Build per-team-game opponent CB unit, then aggregate per team.
    home = schedule.rename(columns={"home_team": "team", "away_team": "opp"})[["week", "team", "opp"]]
    away = schedule.rename(columns={"away_team": "team", "home_team": "opp"})[["week", "team", "opp"]]
    long = pd.concat([home, away], ignore_index=True)
    long = long.merge(cb_units, left_on="opp", right_on="team", suffixes=("", "_drop")).drop(columns=["team_drop"])

    per_team = (
        long.groupby("team")
        .agg(avg_opp_cb=("cb_unit", "mean"), max_opp_cb=("cb_unit", "max"))
        .reset_index()
    )
    top_wr = wrs.sort_values("blended_value", ascending=False).drop_duplicates("team")[["team", "name", "blended_value"]]
    per_team = per_team.merge(top_wr, on="team", how="left").rename(columns={"name": "top_wr", "blended_value": "wr_value"})
    per_team = per_team.sort_values("avg_opp_cb", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(11, 9))
    colors = plt.cm.RdYlGn_r((per_team["avg_opp_cb"] - per_team["avg_opp_cb"].min()) /
                              (per_team["avg_opp_cb"].max() - per_team["avg_opp_cb"].min()))
    bars = ax.barh(range(len(per_team)), per_team["avg_opp_cb"], color=colors, edgecolor="#222")
    league_avg = per_team["avg_opp_cb"].mean()
    ax.axvline(league_avg, color="#888", linestyle="--", linewidth=1, label=f"League avg ({league_avg:.1f})")
    labels = [f"{r.team}  — {r.top_wr}" if pd.notna(r.top_wr) else r.team for r in per_team.itertuples()]
    ax.set_yticks(range(len(per_team)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Avg opponent CB unit score (higher = tougher matchups)")
    ax.set_title("2026 WR Schedule Strength — by team, with WR1 labeled", fontsize=13)
    ax.legend(loc="lower right")
    for i, v in enumerate(per_team["avg_opp_cb"]):
        ax.text(v + 0.15, i, f"{v:.1f}", va="center", fontsize=8, color="#333")
    fig.tight_layout()
    fig.savefig(output.artifact_dir(slug) / "wr_schedule.png", dpi=110)
    plt.close(fig)
    print(f"Saved WR schedule chart for {len(per_team)} teams.")

    # ────────────────────────  Chart 2: Marquee WR-vs-CB matchups  ────────────────────────
    top_wrs = wrs.sort_values("blended_value", ascending=False).head(40).copy()
    # Per-WR per-game matchup
    wr_games = top_wrs.merge(long, on="team")
    wr_games["marquee_score"] = wr_games["blended_value"] * wr_games["cb_unit"] / 100
    wr_games = wr_games.sort_values("marquee_score", ascending=False).reset_index(drop=True)

    # Take top 18 marquee matchups, dedupe within (wr, opp) so the same season-long pairing
    # only shows up once (its highest-scoring week)
    wr_games_unique = wr_games.drop_duplicates(subset=["name", "opp"], keep="first").head(18).reset_index(drop=True)
    wr_games_unique = wr_games_unique.sort_values("marquee_score", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(12, 9))
    labels = [f"W{int(r.week):>2}  {r.name} ({r.team}) vs {r.opp}  [WR {r.blended_value:.0f} × CB {r.cb_unit:.0f}]"
              for r in wr_games_unique.itertuples()]
    colors_m = plt.cm.viridis((wr_games_unique["marquee_score"] - wr_games_unique["marquee_score"].min()) /
                                (wr_games_unique["marquee_score"].max() - wr_games_unique["marquee_score"].min()))
    ax.barh(range(len(wr_games_unique)), wr_games_unique["marquee_score"], color=colors_m, edgecolor="#222")
    ax.set_yticks(range(len(wr_games_unique)))
    ax.set_yticklabels(labels, fontsize=8.5, fontfamily="monospace")
    ax.set_xlabel("Marquee score = WR blended value × opponent CB unit score / 100")
    ax.set_title("2026 Marquee WR-vs-CB Matchups — top 18 (best WR vs best CB unit)", fontsize=13)
    for i, v in enumerate(wr_games_unique["marquee_score"]):
        ax.text(v + 0.4, i, f"{v:.1f}", va="center", fontsize=8, color="#333")
    fig.tight_layout()
    fig.savefig(output.artifact_dir(slug) / "marquee_matchups.png", dpi=110)
    plt.close(fig)
    print(f"Saved marquee matchups chart with {len(wr_games_unique)} entries.")

    # Save the marquee data as a parquet for reuse
    wr_games_unique[["name", "team", "week", "opp", "blended_value", "cb_unit", "marquee_score"]].to_parquet(
        output.artifact_dir(slug) / "marquee_matchups.parquet", index=False
    )
    print("\nTop 10 marquee matchups:")
    print(wr_games_unique.tail(10)[["week", "name", "team", "opp", "blended_value", "cb_unit", "marquee_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
