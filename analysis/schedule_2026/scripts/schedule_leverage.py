"""Schedule Leverage Index — composite of non-opponent-quality schedule burdens.

Combines five environmental / structural dimensions into a single 0-100 score:
  1. Rest differential (negative = bad)
  2. Opponents-off-bye count (more = bad)
  3. Body-clock disadvantage games (more = bad)
  4. Travel miles (more = bad)
  5. Wind exposure mph-games (more = bad)

Each dimension is percentile-ranked within the league (100 = worst burden in that
dimension). Composite = equal-weighted average. Output: data.parquet with the
component scores + composite + leverage_rank.

This is intentionally SEPARATE from implied-wins SoS (opponent quality) — it's
the "non-opponent" lens: who has the toughest schedule environment to navigate,
holding opponent strength constant.
"""
from __future__ import annotations
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')
from _shared import output, teams  # noqa: E402

ROOT = Path("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")
SLUG = "schedule_leverage"


def pct_rank(series: pd.Series, *, ascending: bool) -> pd.Series:
    """Return 0-100 percentile. ascending=True means higher input value -> higher percentile."""
    r = series.rank(method="average", ascending=ascending, pct=True)
    return (r * 100).round(1)


def main() -> None:
    bye = pd.read_parquet(ROOT / "output/bye_leverage/data.parquet")
    bod = pd.read_parquet(ROOT / "output/body_clock/data.parquet")
    trv = pd.read_parquet(ROOT / "output/travel_miles/data.parquet")
    wnd = pd.read_parquet(ROOT / "output/wind_exposure/data.parquet")

    # rest_differential_sum: more NEGATIVE = worse, so ascending=False would put
    # most-negative at the top of percentile. We want "burden score" where high = bad,
    # so we use ascending=False (lower rest_diff -> higher rank).
    rest_burden  = pct_rank(bye["rest_differential_sum"], ascending=False)
    opps_off_bye = pct_rank(bye["opps_off_bye"], ascending=True)
    body_burden  = pct_rank(bod["disadvantage_games"], ascending=True)
    travel_burden= pct_rank(trv["total_miles"], ascending=True)
    wind_burden  = pct_rank(wnd["total_wind_exposure_mph_games"], ascending=True)

    base = pd.DataFrame({"team": bye["team"]})
    df = (base
          .merge(bye[["team", "rest_differential_sum", "opps_off_bye", "bye_week"]], on="team")
          .merge(bod[["team", "disadvantage_games"]], on="team")
          .merge(trv[["team", "total_miles", "intl_miles"]], on="team")
          .merge(wnd[["team", "total_wind_exposure_mph_games"]], on="team"))

    df["rest_burden_pct"]   = df["team"].map(dict(zip(bye["team"], rest_burden)))
    df["off_bye_burden_pct"]= df["team"].map(dict(zip(bye["team"], opps_off_bye)))
    df["body_clock_burden_pct"] = df["team"].map(dict(zip(bod["team"], body_burden)))
    df["travel_burden_pct"] = df["team"].map(dict(zip(trv["team"], travel_burden)))
    df["wind_burden_pct"]   = df["team"].map(dict(zip(wnd["team"], wind_burden)))

    component_cols = ["rest_burden_pct", "off_bye_burden_pct",
                      "body_clock_burden_pct", "travel_burden_pct", "wind_burden_pct"]
    df["leverage_index"] = df[component_cols].mean(axis=1).round(1)

    # Identify each team's top burden — i.e., which dimension is doing the most damage
    pretty = {
        "rest_burden_pct":       "rest",
        "off_bye_burden_pct":    "off-bye opps",
        "body_clock_burden_pct": "body-clock",
        "travel_burden_pct":     "travel",
        "wind_burden_pct":       "wind",
    }
    df["top_burden"] = df[component_cols].idxmax(axis=1).map(pretty)
    df["top_burden_pct"] = df[component_cols].max(axis=1).round(1)

    df["division"] = df["team"].map(teams.DIVISIONS)
    df["leverage_rank"] = df["leverage_index"].rank(ascending=False, method="min").astype(int)
    df = df.sort_values("leverage_index", ascending=False).reset_index(drop=True)

    output.write_data(SLUG, df)

    print(df[["leverage_rank","team","leverage_index","top_burden","top_burden_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
