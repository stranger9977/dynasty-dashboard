"""Wind exposure mapping for the NFL 2026 schedule.

For each outdoor stadium in 2026, pull historical daily wind speeds from
meteostat and compute monthly averages. Indoor / dome stadiums are treated
as a controlled environment (wind = 0). Retractable roofs are also treated
as wind = 0 (assume closed in bad weather).

Per team we compute:
  - total_wind_exposure: sum of expected wind speed (mph) across 17 games
  - high_wind_games_count: outdoor games in Nov/Dec/Jan with monthly avg >= 10 mph
  - outdoor_late_season_games: outdoor games in weeks 14-18
  - dome_games_count: games at dome/retractable venues

Run:
    cd /Users/nick/projects/dynasty-dashboard && \\
        uv run python analysis/schedule_2026/scripts/wind_exposure.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "wind_exposure"

# Wind-exposure thresholds
HIGH_WIND_MPH = 10.0
LATE_SEASON_WEEKS = set(range(14, 19))  # 14..18 inclusive
LATE_WIND_MONTHS = {11, 12, 1}  # Nov, Dec, Jan

# Climate-normal window for meteostat queries
CLIMATE_START = datetime(2015, 1, 1)
CLIMATE_END = datetime(2024, 12, 31)

KMH_TO_MPH = 0.621371

# Local on-disk cache of monthly wind so re-runs are instant.
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "wind_climate_cache.parquet"

# Hardcoded fallback monthly wind speed in mph (rough order-of-magnitude
# numbers for venues meteostat can't reach reliably; used only on fetch failure).
# Keyed by stadium NAME.
FALLBACK_MPH: dict[str, dict[int, float]] = {
    # International outdoor venues — use moderate, slightly elevated wind.
    "Melbourne Cricket Ground": {m: 9.0 for m in range(1, 13)},
    "Stade de France": {m: 9.0 for m in range(1, 13)},
    "FC Bayern Munich Stadium": {m: 8.5 for m in range(1, 13)},
    "Estadio Banorte": {m: 6.0 for m in range(1, 13)},
    "Maracana Stadium": {m: 7.0 for m in range(1, 13)},
}


def _load_cache() -> pd.DataFrame:
    if CACHE_PATH.exists():
        return pd.read_parquet(CACHE_PATH)
    return pd.DataFrame(columns=["lat", "lon", "month", "wspd_mph"])


def _save_cache(df: pd.DataFrame) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_PATH, index=False)


def _round_key(lat: float, lon: float) -> tuple[float, float]:
    """Stable cache key — round to 3 decimals (~110m)."""
    return round(lat, 3), round(lon, 3)


def fetch_monthly_wind_mph(lat: float, lon: float) -> dict[int, float]:
    """Return {month -> avg wind mph} for the given coords, via meteostat.

    Strategy: find the nearest weather station (radius up to 200km), fetch
    daily wspd over the climate window, group by calendar month.

    Returns empty dict if no data available.
    """
    from meteostat import Point, daily, stations, Parameter

    pt = Point(lat, lon)

    # Try the nearest station with growing radius
    for radius in (50000, 100000, 200000):
        nearby = stations.nearby(pt, radius=radius, limit=10)
        if nearby is None or len(nearby) == 0:
            continue
        for sid in nearby.index:
            try:
                ts = daily(sid, CLIMATE_START, CLIMATE_END, parameters=[Parameter.WSPD])
                df = ts.fetch()
            except Exception:
                continue
            if df is None or df.empty or "wspd" not in df.columns:
                continue
            df = df.dropna(subset=["wspd"])
            if len(df) < 365:  # require at least ~1 year of data
                continue
            df = df.copy()
            df["month"] = df.index.month
            monthly_kmh = df.groupby("month")["wspd"].mean()
            monthly_mph = (monthly_kmh * KMH_TO_MPH).to_dict()
            return {int(m): float(v) for m, v in monthly_mph.items()}
    return {}


def build_wind_lookup(sched: pd.DataFrame) -> dict[tuple[str, str], dict[int, float]]:
    """For each unique (stadium_id, stadium_name) in the schedule, produce a
    {month -> avg wind mph} map. Indoor/dome/retractable => all zeros.

    Cached on disk by (lat, lon) so re-runs are fast.
    """
    cache = _load_cache()
    cached_keys: set[tuple[float, float]] = set()
    cache_by_key: dict[tuple[float, float], dict[int, float]] = {}
    for (lat, lon), grp in cache.groupby(["lat", "lon"]):
        key = (round(float(lat), 3), round(float(lon), 3))
        cached_keys.add(key)
        cache_by_key[key] = {int(r.month): float(r.wspd_mph) for r in grp.itertuples()}

    pairs = sched[["stadium_id", "stadium"]].drop_duplicates().to_records(index=False)
    lookup: dict[tuple[str, str], dict[int, float]] = {}
    new_rows: list[dict] = []

    for sid, sname in pairs:
        stadium = teams.resolve_stadium(sid, sname)
        if stadium.roof != "outdoor":
            # Controlled environment — no wind exposure.
            lookup[(sid, sname)] = {m: 0.0 for m in range(1, 13)}
            continue

        key = _round_key(stadium.lat, stadium.lon)
        if key in cache_by_key:
            lookup[(sid, sname)] = cache_by_key[key]
            print(f"  cache hit: {sname} ({stadium.lat:.3f},{stadium.lon:.3f})")
            continue

        print(f"  fetching: {sname} ({stadium.lat:.3f},{stadium.lon:.3f}) ...", flush=True)
        monthly = fetch_monthly_wind_mph(stadium.lat, stadium.lon)
        if not monthly:
            if sname in FALLBACK_MPH:
                monthly = FALLBACK_MPH[sname].copy()
                print(f"    -> using hardcoded fallback for {sname}")
            else:
                print(f"    -> no data; defaulting to 0")
                monthly = {m: 0.0 for m in range(1, 13)}

        # Fill any missing months by interpolation / overall mean
        if monthly:
            mean = float(np.mean(list(monthly.values())))
            for m in range(1, 13):
                monthly.setdefault(m, mean)

        lookup[(sid, sname)] = monthly
        cache_by_key[key] = monthly
        for m, v in monthly.items():
            new_rows.append({"lat": key[0], "lon": key[1], "month": int(m), "wspd_mph": float(v)})

    if new_rows:
        updated = pd.concat([cache, pd.DataFrame(new_rows)], ignore_index=True)
        # dedupe just in case
        updated = updated.drop_duplicates(subset=["lat", "lon", "month"], keep="last")
        _save_cache(updated)
        print(f"  wrote {len(new_rows)} cache rows -> {CACHE_PATH}")

    return lookup


def _month_of(gameday: str) -> int:
    return datetime.strptime(gameday, "%Y-%m-%d").month


def build_team_game_rows(
    sched: pd.DataFrame,
    wind_lookup: dict[tuple[str, str], dict[int, float]],
) -> pd.DataFrame:
    """One row per (game, team perspective). 17 games * 32 teams = 544 rows."""
    records: list[dict] = []
    for _, g in sched.iterrows():
        stadium = teams.resolve_stadium(g["stadium_id"], g["stadium"])
        month = _month_of(g["gameday"])
        wind_mph = wind_lookup[(g["stadium_id"], g["stadium"])].get(month, 0.0)
        is_outdoor = stadium.roof == "outdoor"
        late_season = int(g["week"]) in LATE_SEASON_WEEKS
        high_wind = is_outdoor and (month in LATE_WIND_MONTHS) and (wind_mph >= HIGH_WIND_MPH)
        for side in ("home", "away"):
            team = g[f"{side}_team"]
            opp = g["away_team"] if side == "home" else g["home_team"]
            records.append(
                {
                    "game_id": g["game_id"],
                    "week": int(g["week"]),
                    "gameday": g["gameday"],
                    "month": month,
                    "team": team,
                    "opp": opp,
                    "side": side,
                    "stadium_id": g["stadium_id"],
                    "stadium": g["stadium"],
                    "roof": stadium.roof,
                    "is_outdoor": is_outdoor,
                    "wind_mph": float(wind_mph),
                    "high_wind_game": bool(high_wind),
                    "outdoor_late_season": bool(is_outdoor and late_season),
                }
            )
    return pd.DataFrame(records)


def build_summary(rows: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        rows.groupby("team")
        .agg(
            total_wind_exposure_mph_games=("wind_mph", "sum"),
            high_wind_games_count=("high_wind_game", "sum"),
            outdoor_late_season_games=("outdoor_late_season", "sum"),
            dome_games_count=("is_outdoor", lambda s: int((~s).sum())),
            games=("week", "count"),
        )
        .reset_index()
    )
    grouped["high_wind_games_count"] = grouped["high_wind_games_count"].astype(int)
    grouped["outdoor_late_season_games"] = grouped["outdoor_late_season_games"].astype(int)
    grouped["dome_games_count"] = grouped["dome_games_count"].astype(int)
    grouped["total_wind_exposure_mph_games"] = grouped["total_wind_exposure_mph_games"].round(2)
    grouped = grouped[
        [
            "team",
            "total_wind_exposure_mph_games",
            "high_wind_games_count",
            "outdoor_late_season_games",
            "dome_games_count",
        ]
    ].sort_values("team").reset_index(drop=True)
    return grouped


def make_chart(df: pd.DataFrame, path) -> None:
    plot_df = df.sort_values("total_wind_exposure_mph_games", ascending=True).reset_index(drop=True)
    colors = []
    for v in plot_df["total_wind_exposure_mph_games"]:
        if v >= 130:
            colors.append("#d62728")  # red — heavy
        elif v >= 100:
            colors.append("#ff7f0e")  # orange — elevated
        elif v >= 60:
            colors.append("#7f7f7f")  # grey — moderate
        else:
            colors.append("#2ca02c")  # green — sheltered

    fig, ax = plt.subplots(figsize=(11, 11))
    y = np.arange(len(plot_df))
    ax.barh(
        y,
        plot_df["total_wind_exposure_mph_games"],
        color=colors,
        edgecolor="black",
        linewidth=0.4,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["team"], fontsize=9)
    ax.set_xlabel("Total wind exposure (sum of expected mph across 17 games)")
    ax.set_title(
        "NFL 2026 Wind Exposure by Team\n"
        "(outdoor venues only; indoor/dome/retractable = 0)"
    )

    pad = plot_df["total_wind_exposure_mph_games"].max() * 0.01 + 0.5
    for i, (total, hw, dome) in enumerate(
        zip(
            plot_df["total_wind_exposure_mph_games"],
            plot_df["high_wind_games_count"],
            plot_df["dome_games_count"],
        )
    ):
        ax.text(
            total + pad,
            i,
            f"{total:.1f}  (HW:{int(hw)} / dome:{int(dome)})",
            va="center",
            ha="left",
            fontsize=8,
        )

    from matplotlib.patches import Patch

    legend_elems = [
        Patch(facecolor="#d62728", edgecolor="black", label="Heavy (≥130)"),
        Patch(facecolor="#ff7f0e", edgecolor="black", label="Elevated (100-129)"),
        Patch(facecolor="#7f7f7f", edgecolor="black", label="Moderate (60-99)"),
        Patch(facecolor="#2ca02c", edgecolor="black", label="Sheltered (<60)"),
    ]
    ax.legend(handles=legend_elems, loc="lower right", framealpha=0.9)
    ax.margins(x=0.18)
    ax.grid(axis="x", linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ----- Findings helpers ------------------------------------------------------

# QB starters by team (best guess as of May 2026). Used for color in findings.
QB_BY_TEAM: dict[str, str] = {
    "ARI": "Kyler Murray", "ATL": "Michael Penix Jr.", "BAL": "Lamar Jackson",
    "BUF": "Josh Allen", "CAR": "Bryce Young", "CHI": "Caleb Williams",
    "CIN": "Joe Burrow", "CLE": "Dillon Gabriel", "DAL": "Dak Prescott",
    "DEN": "Bo Nix", "DET": "Jared Goff", "GB": "Jordan Love",
    "HOU": "C.J. Stroud", "IND": "Anthony Richardson", "JAX": "Trevor Lawrence",
    "KC": "Patrick Mahomes", "LA": "Matthew Stafford", "LAC": "Justin Herbert",
    "LV": "Geno Smith", "MIA": "Tua Tagovailoa", "MIN": "J.J. McCarthy",
    "NE": "Drake Maye", "NO": "Tyler Shough", "NYG": "Jaxson Dart",
    "NYJ": "Justin Fields", "PHI": "Jalen Hurts", "PIT": "Aaron Rodgers",
    "SEA": "Sam Darnold", "SF": "Brock Purdy", "TB": "Baker Mayfield",
    "TEN": "Cam Ward", "WAS": "Jayden Daniels",
}


def _fmt_game(row: pd.Series) -> str:
    side = row["side"]
    if side == "away":
        descriptor = f"{row['team']} at {row['opp']}"
    else:
        descriptor = f"{row['opp']} at {row['team']}"
    return f"{descriptor} wk {int(row['week'])} ({row['wind_mph']:.1f} mph at {row['stadium']})"


def build_findings(summary: pd.DataFrame, rows: pd.DataFrame) -> str:
    # Most-exposed teams (highest total_wind)
    worst = summary.sort_values("total_wind_exposure_mph_games", ascending=False).reset_index(drop=True)
    best = summary.sort_values("total_wind_exposure_mph_games", ascending=True).reset_index(drop=True)

    top5 = worst.head(5)
    bot5 = best.head(5)

    # Specific high-wind matchup examples — find the windiest single games in the season.
    outdoor_rows = rows[rows["is_outdoor"]].copy()
    # Dedup by game_id (we have two perspective rows per game)
    unique_games = outdoor_rows.drop_duplicates(subset=["game_id"]).copy()
    windiest = unique_games.sort_values("wind_mph", ascending=False).head(6)

    # Build per-team example high-wind games for the top-3 most-exposed
    def team_high_wind_example(team: str) -> str:
        sub = rows[(rows["team"] == team) & rows["is_outdoor"]].sort_values("wind_mph", ascending=False)
        if sub.empty:
            return "n/a"
        return _fmt_game(sub.iloc[0])

    top_lines = []
    for _, r in top5.iterrows():
        qb = QB_BY_TEAM.get(r["team"], "QB1")
        ex = team_high_wind_example(r["team"])
        top_lines.append(
            f"- **{r['team']} ({qb})** — total exposure {r['total_wind_exposure_mph_games']:.1f} mph-games, "
            f"{int(r['high_wind_games_count'])} high-wind games, "
            f"{int(r['outdoor_late_season_games'])} outdoor wk 14-18. "
            f"Worst: {ex}."
        )

    bot_lines = []
    for _, r in bot5.iterrows():
        qb = QB_BY_TEAM.get(r["team"], "QB1")
        bot_lines.append(
            f"- **{r['team']} ({qb})** — {r['total_wind_exposure_mph_games']:.1f} mph-games, "
            f"{int(r['dome_games_count'])} indoor games"
        )

    matchup_lines = []
    for _, r in windiest.iterrows():
        matchup_lines.append(f"- {_fmt_game(r)}")

    total_outdoor = int(rows["is_outdoor"].sum() // 2)  # each game has 2 rows
    total_high_wind = int(unique_games[unique_games["high_wind_game"]].shape[0])
    avg_total = float(summary["total_wind_exposure_mph_games"].mean())

    md = f"""# Wind Exposure — 2026 Schedule

Wind exposure measures the sum of expected wind speed (mph) across each team's
17 games, using historical monthly normals from meteostat. Dome and retractable
venues contribute 0. High-wind games are outdoor Nov/Dec/Jan games with monthly
average wind ≥ {HIGH_WIND_MPH:.0f} mph.

League averages: total exposure {avg_total:.1f} mph-games per team; {total_outdoor}
outdoor games league-wide; {total_high_wind} flagged as high-wind matchups.

## Most-exposed QBs (worst wind schedules)

{chr(10).join(top_lines)}

## Dome-friendly schedules (least wind)

{chr(10).join(bot_lines)}

## Windiest individual matchups

{chr(10).join(matchup_lines)}

## Fantasy takeaway

QBs and WRs at the top of this list face structural wind headwinds —
especially deep-ball passers like {QB_BY_TEAM.get(top5.iloc[0]['team'], 'QB1')}
and {QB_BY_TEAM.get(top5.iloc[1]['team'], 'QB1')} who lean on vertical concepts.
By contrast, the dome-friendly group above ({', '.join(bot5['team'].tolist()[:3])})
plays a meaningful chunk of games indoors and gets a near-neutral wind environment
for fantasy production. The late-season weeks 14-18 — fantasy playoffs — are where
the wind delta matters most; teams with several outdoor cold-weather road games in
that window (see "Worst" examples above) are downgrade candidates for win-now
fantasy teams chasing rings.
"""
    return md


def main() -> None:
    sched = nflverse.load_schedule_2026()
    if "game_type" in sched.columns:
        sched = sched[sched["game_type"] == "REG"].copy()
    assert len(sched) == 272, f"expected 272 reg-season games, got {len(sched)}"

    print("Building wind climate lookup ...")
    wind_lookup = build_wind_lookup(sched)
    print(f"  -> {len(wind_lookup)} unique stadiums covered")

    rows = build_team_game_rows(sched, wind_lookup)
    assert len(rows) == 544, f"expected 544 team-game rows, got {len(rows)}"

    summary = build_summary(rows)
    assert len(summary) == 32, f"expected 32 teams, got {len(summary)}"

    data_path = output.write_data(SLUG, summary)
    chart_p = output.chart_path(SLUG)
    make_chart(summary, chart_p)
    findings_md = build_findings(summary, rows)
    findings_path = output.write_findings(SLUG, findings_md)

    print()
    print(f"Wrote data:     {data_path}  ({len(summary)} rows)")
    print(f"Wrote chart:    {chart_p}")
    print(f"Wrote findings: {findings_path}")
    print()
    print(summary.sort_values("total_wind_exposure_mph_games", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
