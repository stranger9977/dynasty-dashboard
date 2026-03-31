import json
import re

import pandas as pd
import requests

from config import KTC_DYNASTY_URL

POSITION_MAP = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "PK", 6: "DEF"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def extract_players_array(html: str) -> list[dict]:
    match = re.search(r"var\s+playersArray\s*=\s*(\[.*?\]);", html, re.DOTALL)
    if not match:
        raise ValueError("Could not find playersArray in KTC page HTML")
    return json.loads(match.group(1))


def fetch_ktc() -> pd.DataFrame:
    resp = requests.get(KTC_DYNASTY_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    players = extract_players_array(resp.text)

    rows = []
    for p in players:
        position = POSITION_MAP.get(p.get("positionID"), p.get("position", ""))
        if position not in ("QB", "RB", "WR", "TE"):
            continue

        sf = p.get("superflexValues", {})
        # Use base superflex values (not TEP) since FantasyCalc doesn't
        # support TE Premium — using TEP here would create a false
        # disagreement on every TE.
        vals = sf

        rows.append({
            "name": p.get("playerName"),
            "position": position,
            "team": p.get("team"),
            "age": p.get("age"),
            "years_exp": p.get("seasonsExperience"),
            "is_rookie": p.get("rookie", False),
            "mfl_id": str(p.get("mflid", "")),
            "ktc_id": p.get("playerID"),
            "ktc_slug": p.get("slug"),
            "ktc_value": vals.get("value"),
            "ktc_rank": vals.get("rank"),
            "ktc_pos_rank": vals.get("positionalRank"),
            "ktc_tier": vals.get("overallTier"),
            "ktc_pos_tier": vals.get("positionalTier"),
            "ktc_trend_7d": sf.get("overall7DayTrend", 0),
            "college": p.get("college"),
            "draft_year": p.get("draftYear"),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("ktc_rank").reset_index(drop=True)
    return df
