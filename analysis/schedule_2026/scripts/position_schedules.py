"""Build per-position schedule-strength tables for RB and TE.

Each team's top player at the position (by dynasty value) paired with their team's
opponent SoS for that position — pulled from the position_sos analysis output.
"""
from __future__ import annotations
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, '/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026')
from _shared import output  # noqa: E402

ROOT = Path("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

TEAM_FIX = {"GBP": "GB", "KCC": "KC", "LVR": "LV", "NOS": "NO",
            "SFO": "SF", "TBB": "TB", "LAR": "LA"}


def top_player_per_team(position: str) -> pd.DataFrame:
    """Return top dynasty-value player per team for given position."""
    m = pd.read_parquet("/Users/nick/projects/dynasty-dashboard/data/merged.parquet")
    pos_players = m[(m["position"] == position) & (m["team"] != "FA")].copy()
    pos_players["team"] = pos_players["team"].replace(TEAM_FIX)
    return (pos_players.sort_values("blended_value", ascending=False)
            .drop_duplicates("team")[["name", "team", "blended_value", "age"]]
            .rename(columns={"name": "top_player"}))


def main() -> None:
    pos_sos = pd.read_parquet(ROOT / "output/position_sos/data.parquet")

    for position, score_col, fpa_col, slug in [
        ("RB", "rb_sos_score", "rb_opp_fpa", "rb_schedule"),
        ("TE", "te_sos_score", "te_opp_fpa", "te_schedule"),
    ]:
        top = top_player_per_team(position)
        df = pos_sos[["team", score_col, fpa_col]].merge(top, on="team", how="left")
        df = df.rename(columns={score_col: "sos_score", fpa_col: "opp_fpa"})
        df = df.sort_values("sos_score", ascending=False).reset_index(drop=True)
        out_dir = ROOT / "output" / "position_schedules"
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_dir / f"{slug}.parquet", index=False)
        print(f"[{position}] top-5 toughest:")
        print(df.head(5)[["team", "top_player", "sos_score", "opp_fpa", "blended_value"]].to_string(index=False))
        print(f"[{position}] top-5 easiest:")
        print(df.tail(5).iloc[::-1][["team", "top_player", "sos_score", "opp_fpa", "blended_value"]].to_string(index=False))
        print()


if __name__ == "__main__":
    main()
