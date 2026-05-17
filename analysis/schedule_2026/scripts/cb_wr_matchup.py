"""CB/WR matchup index for 2026 (v1, team-level CB unit strength).

Methodology:
1. Scrape Ourlads team depth charts for current CB1 (LCB), CB2 (RCB), and Nickel (NB).
   Fallback: 2025 nflverse rosters filtered to depth_chart_position == 'CB' if scrape fails.
2. Compute per-CB quality from nflverse PBP 2024+2025: pass deflections + interceptions
   per game played, recency-weighted (2025=0.6, 2024=0.4). Normalized to a 0-100 score
   (population percentile, higher = better coverage). Unmatched/rookie defaults: 50.
   NOTE: PFR was blocked (403) for this run, so we substitute PBP-derived coverage stats.
3. Team CB unit score = 0.45*cb1 + 0.35*cb2 + 0.20*nickel.
4. WR schedule difficulty: for each WR on a 2025 roster (any depth_chart_position == 'WR'
   restricted to the top 3 per team by offensive snap proxy — falling back to first 3
   alphabetically), sum opposing CB unit scores across their 17 games.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from _shared import nflverse, output, teams

SLUG = "cb_wr_matchup"

# Map nflverse team abbr -> Ourlads URL abbr (mostly the same)
OURLADS_TEAM_ABBR = {
    "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF",
    "CAR": "CAR", "CHI": "CHI", "CIN": "CIN", "CLE": "CLE",
    "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GB": "GB",
    "HOU": "HOU", "IND": "IND", "JAX": "JAX", "KC": "KC",
    "LA": "LAR", "LAC": "LAC", "LV": "LV", "MIA": "MIA",
    "MIN": "MIN", "NE": "NE", "NO": "NO", "NYG": "NYG",
    "NYJ": "NYJ", "PHI": "PHI", "PIT": "PIT", "SEA": "SEA",
    "SF": "SF", "TB": "TB", "TEN": "TEN", "WAS": "WAS",
}

SEASON_WEIGHTS = {2025: 0.6, 2024: 0.4}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


# -----------------------------
# Part 1: scrape CB depth charts
# -----------------------------
def _flip_lastfirst(name: str) -> str:
    """'Witherspoon, Devon 23/1' -> 'Devon Witherspoon'."""
    name = re.sub(r"\s+\S+/\S+\s*$", "", name)  # strip trailing "23/1" or "U/NO"
    name = re.sub(r"\s+[A-Z]{2,3}\d{2}\s*$", "", name)  # strip e.g. "SF24"
    name = re.sub(r"\s+[A-Z]{2,3}\d{2}\s*$", "", name)
    if "," in name:
        last, _, first = name.partition(",")
        return f"{first.strip()} {last.strip()}".strip()
    return name.strip()


def scrape_ourlads_team(abbr: str) -> dict:
    """Return {'cb1': name, 'cb2': name, 'nickel': name} or empty dict on failure."""
    url = f"https://www.ourlads.com/nfldepthcharts/depthchart/{abbr}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
    except Exception as e:
        print(f"  ourlads {abbr}: {e}")
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    out = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            pos = cells[0].get_text(strip=True)
            if pos in ("LCB", "RCB", "NB"):
                # First non-empty player name lives in cells[2] typically (cells[1] is jersey)
                texts = [c.get_text(strip=True) for c in cells]
                # Find the first cell after the position that looks like a name
                player = None
                for t in texts[1:]:
                    if t and not t.isdigit() and "," in t:
                        player = _flip_lastfirst(t)
                        break
                if not player:
                    continue
                if pos == "LCB":
                    out.setdefault("cb1", player)
                elif pos == "RCB":
                    out.setdefault("cb2", player)
                elif pos == "NB":
                    out.setdefault("nickel", player)
    return out


def scrape_all_depth_charts() -> pd.DataFrame:
    rows = []
    failures = []
    for team in teams.ALL_TEAMS:
        abbr = OURLADS_TEAM_ABBR[team]
        info = scrape_ourlads_team(abbr)
        if not info:
            failures.append(team)
        rows.append({
            "team": team,
            "cb1_name": info.get("cb1"),
            "cb2_name": info.get("cb2"),
            "nickel_name": info.get("nickel"),
        })
        # Be polite — small delay
        time.sleep(0.25)
    df = pd.DataFrame(rows)
    print(f"  ourlads success: {32 - len(failures)}/32 teams")
    if failures:
        print(f"  failures: {failures}")
    return df


def fallback_from_rosters(depth_df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing CBs from 2025 rosters (use first three CBs per team by jersey)."""
    r25 = nflverse.load_rosters(2025)
    cbs = r25[
        (r25["position"] == "DB")
        & (r25["depth_chart_position"] == "CB")
        & r25["team"].notna()
    ].copy()
    cbs = cbs.sort_values(["team", "jersey_number"])
    fill = {}
    for team, grp in cbs.groupby("team"):
        names = grp["full_name"].tolist()
        fill[team] = names[:3] + [None, None, None]

    out = depth_df.copy()
    for i, row in out.iterrows():
        team = row["team"]
        names = fill.get(team, [None, None, None])
        if pd.isna(row["cb1_name"]) or not row["cb1_name"]:
            out.at[i, "cb1_name"] = names[0]
        if pd.isna(row["cb2_name"]) or not row["cb2_name"]:
            out.at[i, "cb2_name"] = names[1]
        if pd.isna(row["nickel_name"]) or not row["nickel_name"]:
            out.at[i, "nickel_name"] = names[2]
    return out


# -----------------------------
# Part 2: CB quality scoring
# -----------------------------
def build_cb_quality_table(seasons=(2024, 2025)) -> pd.DataFrame:
    """Aggregate per-player coverage stats from PBP, recency-weighted.

    Returns df with: gsis_id, last_first_lower, full_name_lower, quality_score (0-100).
    """
    frames = []
    for season in seasons:
        pbp = nflverse.load_pbp([season])
        pbp = pbp[pbp["season_type"] == "REG"].copy()

        # Pass deflections from pass_defense_1 and pass_defense_2
        pd_rows = []
        for col_id, col_name in [
            ("pass_defense_1_player_id", "pass_defense_1_player_name"),
            ("pass_defense_2_player_id", "pass_defense_2_player_name"),
        ]:
            sub = pbp[pbp[col_id].notna()][[col_id, col_name, "defteam", "game_id"]].copy()
            sub.columns = ["player_id", "player_name", "defteam", "game_id"]
            sub["pd"] = 1
            pd_rows.append(sub)
        pd_df = pd.concat(pd_rows, ignore_index=True)
        pd_agg = pd_df.groupby(["player_id"], as_index=False).agg(
            pds=("pd", "sum"),
            games_pd=("game_id", "nunique"),
            name_pd=("player_name", "first"),
        )

        # INTs
        ints = pbp[pbp["interception_player_id"].notna()][
            ["interception_player_id", "interception_player_name", "game_id"]
        ].copy()
        ints.columns = ["player_id", "player_name", "game_id"]
        ints["int_"] = 1
        int_agg = ints.groupby("player_id", as_index=False).agg(
            ints_=("int_", "sum"),
            games_int=("game_id", "nunique"),
            name_int=("player_name", "first"),
        )

        # Solo tackles by defender (helps with games played)
        st_rows = []
        for col_id, col_name in [
            ("solo_tackle_1_player_id", "solo_tackle_1_player_name"),
            ("solo_tackle_2_player_id", "solo_tackle_2_player_name"),
        ]:
            sub = pbp[pbp[col_id].notna()][[col_id, col_name, "game_id"]].copy()
            sub.columns = ["player_id", "player_name", "game_id"]
            sub["st"] = 1
            st_rows.append(sub)
        st_df = pd.concat(st_rows, ignore_index=True)
        st_agg = st_df.groupby("player_id", as_index=False).agg(
            solos=("st", "sum"),
            games_st=("game_id", "nunique"),
            name_st=("player_name", "first"),
        )

        # Merge
        m = pd_agg.merge(int_agg, on="player_id", how="outer").merge(
            st_agg, on="player_id", how="outer"
        )
        m["pds"] = m["pds"].fillna(0)
        m["ints_"] = m["ints_"].fillna(0)
        m["solos"] = m["solos"].fillna(0)
        # games played: take max across stats (any appearance counts as a game)
        m["games"] = m[["games_pd", "games_int", "games_st"]].max(axis=1).fillna(0)
        # Best name available
        m["player_name"] = m["name_pd"].fillna(m["name_int"]).fillna(m["name_st"])
        m["season"] = season
        frames.append(m[["player_id", "player_name", "season", "pds", "ints_", "solos", "games"]])

    raw = pd.concat(frames, ignore_index=True)
    # Apply recency weighting per stat & games
    raw["weight"] = raw["season"].map(SEASON_WEIGHTS)
    # Sum weighted stats; weight games similarly so per-game stays comparable.
    raw["w_pds"] = raw["pds"] * raw["weight"]
    raw["w_ints"] = raw["ints_"] * raw["weight"]
    raw["w_solos"] = raw["solos"] * raw["weight"]
    raw["w_games"] = raw["games"] * raw["weight"]
    agg = raw.groupby(["player_id"], as_index=False).agg(
        player_name=("player_name", "first"),
        w_pds=("w_pds", "sum"),
        w_ints=("w_ints", "sum"),
        w_solos=("w_solos", "sum"),
        w_games=("w_games", "sum"),
    )
    # Per-game rates (avoid divide by zero)
    agg["pds_pg"] = agg["w_pds"] / agg["w_games"].clip(lower=0.5)
    agg["ints_pg"] = agg["w_ints"] / agg["w_games"].clip(lower=0.5)
    agg["solos_pg"] = agg["w_solos"] / agg["w_games"].clip(lower=0.5)
    # Require minimum playing time to be considered "established"
    agg["min_games_ok"] = agg["w_games"] >= 4

    # Coverage composite (pre-normalization):
    # 0.55 * (pds_pg + 0.8*ints_pg) + 0.45 * solos_pg
    # PDs are the strongest signal for coverage; solo tackles fill in for nickels/run support
    agg["composite_raw"] = 0.55 * (agg["pds_pg"] + 0.8 * agg["ints_pg"]) + 0.45 * agg["solos_pg"]

    # Percentile normalize within the qualified population
    qualified = agg[agg["min_games_ok"]].copy()
    if len(qualified) > 5:
        qualified["quality_score"] = (
            qualified["composite_raw"].rank(method="average", pct=True) * 100
        )
    else:
        qualified["quality_score"] = 50.0
    # Merge back; unqualified get NaN -> 50 default later
    score_map = dict(zip(qualified["player_id"], qualified["quality_score"]))
    agg["quality_score"] = agg["player_id"].map(score_map)

    return agg[["player_id", "player_name", "quality_score", "w_games"]]


# -----------------------------
# Name matching helpers
# -----------------------------
def _norm_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_roster_lookup() -> dict:
    """Build name -> gsis_id lookup using 2024 + 2025 rosters, DB only."""
    lookup = {}
    for season in (2024, 2025):
        r = nflverse.load_rosters(season)
        r = r[r["position"] == "DB"].dropna(subset=["full_name", "gsis_id"])
        for _, row in r.iterrows():
            key = _norm_name(row["full_name"])
            lookup[key] = row["gsis_id"]
            # Also try football_name variant
            if pd.notna(row.get("football_name")):
                k2 = _norm_name(f"{row['football_name']} {row['last_name']}")
                lookup.setdefault(k2, row["gsis_id"])
    return lookup


def pbp_name_lookup(quality: pd.DataFrame) -> dict:
    """gsis_id -> quality_score map keyed by 'F.Last' style PBP names."""
    out = {}
    for _, row in quality.iterrows():
        if pd.notna(row["quality_score"]):
            out[row["player_id"]] = row["quality_score"]
    return out


def score_player(name: str | None, roster_lookup: dict, score_map: dict) -> tuple[float, bool]:
    """(score, matched) - defaults to 50 if no match."""
    if not name or (isinstance(name, float) and pd.isna(name)):
        return 50.0, False
    key = _norm_name(name)
    gsis = roster_lookup.get(key)
    if gsis and gsis in score_map:
        return float(score_map[gsis]), True
    # Try last-name only fallback
    parts = key.split()
    if len(parts) >= 2:
        for k, v in roster_lookup.items():
            if k.endswith(" " + parts[-1]) and parts[0][:1] == k.split()[0][:1]:
                if v in score_map:
                    return float(score_map[v]), True
    return 50.0, False


# -----------------------------
# Part 3: assemble team CB unit
# -----------------------------
def build_team_table(depth_df: pd.DataFrame, roster_lookup: dict, score_map: dict) -> tuple[pd.DataFrame, dict]:
    rows = []
    match_stats = {"matched": 0, "defaulted": 0}
    for _, r in depth_df.iterrows():
        c1, m1 = score_player(r["cb1_name"], roster_lookup, score_map)
        c2, m2 = score_player(r["cb2_name"], roster_lookup, score_map)
        cn, mn = score_player(r["nickel_name"], roster_lookup, score_map)
        for m in (m1, m2, mn):
            match_stats["matched" if m else "defaulted"] += 1
        unit = 0.45 * c1 + 0.35 * c2 + 0.20 * cn
        rows.append({
            "team": r["team"],
            "cb1_name": r["cb1_name"],
            "cb1_score": round(c1, 1),
            "cb2_name": r["cb2_name"],
            "cb2_score": round(c2, 1),
            "nickel_name": r["nickel_name"],
            "nickel_score": round(cn, 1),
            "unit_score": round(unit, 1),
        })
    return pd.DataFrame(rows), match_stats


# -----------------------------
# Part 4: WR schedule difficulty
# -----------------------------
def build_wr_schedule(team_df: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    """For each top-3 WR per team, total opposing CB unit score across their schedule."""
    unit_map = dict(zip(team_df["team"], team_df["unit_score"]))

    # Build opp list per team
    opp_rows = []
    for _, g in sched.iterrows():
        if str(g.get("game_type", "REG")) != "REG":
            continue
        opp_rows.append({"team": g["home_team"], "opp": g["away_team"]})
        opp_rows.append({"team": g["away_team"], "opp": g["home_team"]})
    opp_df = pd.DataFrame(opp_rows)

    # Top WRs per team from 2025 roster (first 3 by jersey_number — proxy for usage)
    r25 = nflverse.load_rosters(2025)
    wrs = r25[(r25["position"] == "WR") & r25["team"].notna()].copy()
    wrs = wrs.sort_values(["team", "jersey_number"])
    top_wrs = wrs.groupby("team").head(3)[["full_name", "team", "jersey_number"]]

    rows = []
    for _, w in top_wrs.iterrows():
        team = w["team"]
        opps = opp_df[opp_df["team"] == team]["opp"].tolist()
        total = sum(unit_map.get(o, 50.0) for o in opps)
        avg = total / len(opps) if opps else 50.0
        rows.append({
            "wr_name": w["full_name"],
            "team": team,
            "n_games": len(opps),
            "total_opp_cb_score": round(total, 1),
            "avg_opp_cb_score": round(avg, 2),
        })
    return pd.DataFrame(rows).sort_values("avg_opp_cb_score", ascending=False).reset_index(drop=True)


# -----------------------------
# Plotting & findings
# -----------------------------
def plot_unit_scores(df: pd.DataFrame, path) -> None:
    d = df.sort_values("unit_score", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8, 11))
    colors = plt.cm.RdYlGn(d["unit_score"] / 100.0)
    ax.barh(d["team"], d["unit_score"], color=colors, edgecolor="black", linewidth=0.4)
    for i, v in enumerate(d["unit_score"]):
        ax.text(v + 0.7, i, f"{v:.1f}", va="center", fontsize=8)
    ax.set_xlim(0, 100)
    ax.set_xlabel("CB unit score (0-100, higher = better coverage)")
    ax.set_title(
        "2026 Team CB Unit Strength\n"
        "0.45·CB1 + 0.35·CB2 + 0.20·Nickel, from PBP 2024-25 (recency-weighted)",
        fontsize=11,
    )
    ax.tick_params(axis="y", labelsize=8)
    ax.axvline(50, linestyle="--", color="gray", linewidth=0.6, alpha=0.6)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def build_findings(team_df: pd.DataFrame, wr_df: pd.DataFrame, match_stats: dict,
                   ourlads_ok: int, used_pfr: bool) -> str:
    top5 = team_df.sort_values("unit_score", ascending=False).head(5)
    bot5 = team_df.sort_values("unit_score", ascending=True).head(5)

    top_lines = "\n".join(
        f"- **{r['team']}** ({r['unit_score']:.1f}) — "
        f"{r['cb1_name']} / {r['cb2_name']} / {r['nickel_name']}"
        for _, r in top5.iterrows()
    )
    bot_lines = "\n".join(
        f"- **{r['team']}** ({r['unit_score']:.1f}) — "
        f"{r['cb1_name']} / {r['cb2_name']} / {r['nickel_name']}"
        for _, r in bot5.iterrows()
    )

    if wr_df is not None and len(wr_df):
        # Toughest schedule = highest avg_opp_cb_score
        toughest = wr_df.head(3)
        easiest = wr_df.tail(3).iloc[::-1]
        tough_lines = "\n".join(
            f"- **{r['wr_name']}** ({r['team']}) — avg opp CB unit {r['avg_opp_cb_score']:.1f}"
            for _, r in toughest.iterrows()
        )
        easy_lines = "\n".join(
            f"- **{r['wr_name']}** ({r['team']}) — avg opp CB unit {r['avg_opp_cb_score']:.1f}"
            for _, r in easiest.iterrows()
        )
        wr_section = (
            "\n\n## WR schedule difficulty (top 3 WRs per team)\n\n"
            f"**Toughest CB schedules:**\n{tough_lines}\n\n"
            f"**Easiest CB schedules:**\n{easy_lines}\n"
        )
    else:
        wr_section = "\n\n## WR schedule difficulty\nSkipped (scope reduction).\n"

    total_slots = match_stats["matched"] + match_stats["defaulted"]
    match_pct = 100.0 * match_stats["matched"] / max(total_slots, 1)

    scope_note = (
        "## Scope notes\n\n"
        f"- **Ourlads scrape:** {ourlads_ok}/32 teams returned depth chart data; "
        "remaining teams filled from 2025 nflverse rosters (depth_chart_position=='CB'), "
        "ordered by jersey number as a proxy for depth.\n"
        f"- **PFR advanced defense was BLOCKED (HTTP 403) for both 2024 and 2025**, so the "
        "spec'd CB-quality composite (passer rating allowed, comp%, yards/target) was "
        "**replaced with a PBP-derived composite**: pass deflections per game (55%) + "
        "interceptions per game (weighted within that 55%) + solo tackles per game (45%). "
        "Scores are population percentiles among DBs with >=4 weighted games of PBP "
        "activity in 2024-2025; weighting 2025=0.6, 2024=0.4. Players below the activity "
        "threshold default to 50 (median).\n"
        f"- **CB-name match rate:** {match_stats['matched']}/{total_slots} "
        f"({match_pct:.0f}%); {match_stats['defaulted']} slots defaulted to 50. Rookies "
        "and lightly-used CBs are the main miss categories.\n"
        "- **WR list:** top 3 WRs per team from 2025 rosters, ordered by jersey number "
        "(no separate per-route or snap-share data used).\n"
    )

    return (
        "# CB/WR Matchup Index — 2026 (v1, team-level)\n\n"
        "Per-team CB unit strength derived from 2024-2025 PBP coverage stats applied to "
        "current depth charts. CB unit = 0.45·CB1 + 0.35·CB2 + 0.20·Nickel. WR schedule "
        "difficulty is the average opposing CB unit score across each WR's 17-game "
        "2026 schedule (higher = tougher).\n\n"
        "## Top 5 CB units\n\n" + top_lines + "\n\n"
        "## Bottom 5 CB units\n\n" + bot_lines +
        wr_section +
        "\n" + scope_note
    )


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    print("scraping Ourlads depth charts for 32 teams (this takes ~10s)...")
    depth_df = scrape_all_depth_charts()
    ourlads_ok = depth_df[["cb1_name", "cb2_name", "nickel_name"]].notna().any(axis=1).sum()
    print(f"  depth charts populated for {ourlads_ok}/32 teams")

    print("filling gaps from 2025 rosters...")
    depth_df = fallback_from_rosters(depth_df)
    print(f"  CB1 missing: {depth_df['cb1_name'].isna().sum()}")
    print(f"  CB2 missing: {depth_df['cb2_name'].isna().sum()}")
    print(f"  Nickel missing: {depth_df['nickel_name'].isna().sum()}")

    print("computing CB quality from PBP 2024+2025...")
    quality = build_cb_quality_table()
    matched_quality = quality["quality_score"].notna().sum()
    print(f"  {matched_quality} qualified DB-population scores assigned")

    print("matching CB names...")
    roster_lookup = build_roster_lookup()
    score_map = pbp_name_lookup(quality)
    team_df, match_stats = build_team_table(depth_df, roster_lookup, score_map)
    print(f"  matched: {match_stats['matched']}/{sum(match_stats.values())}")

    assert len(team_df) == 32

    print("computing WR schedule difficulty...")
    sched = nflverse.load_schedule_2026()
    wr_df = build_wr_schedule(team_df, sched)
    print(f"  {len(wr_df)} WR schedules built")

    print("writing outputs...")
    data_path = output.write_data(SLUG, team_df)
    wr_path = output.write_data(SLUG, wr_df, filename="wr_schedules.parquet")
    chart_p = output.chart_path(SLUG)
    plot_unit_scores(team_df, chart_p)
    findings = build_findings(team_df, wr_df, match_stats, int(ourlads_ok), used_pfr=False)
    findings_path = output.write_findings(SLUG, findings)

    print(f"wrote {data_path}")
    print(f"wrote {wr_path}")
    print(f"wrote {chart_p}")
    print(f"wrote {findings_path}")
    print()
    print("=== top 5 CB units ===")
    print(team_df.sort_values("unit_score", ascending=False).head(5).to_string(index=False))
    print()
    print("=== bottom 5 CB units ===")
    print(team_df.sort_values("unit_score", ascending=True).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
