import pandas as pd
import requests

from config import FANTASYCALC_URL, NUM_QBS, NUM_TEAMS, PPR, IS_DYNASTY


def fetch_fantasycalc() -> pd.DataFrame:
    params = {
        "isDynasty": str(IS_DYNASTY).lower(),
        "numQbs": NUM_QBS,
        "numTeams": NUM_TEAMS,
        "ppr": PPR,
    }
    resp = requests.get(FANTASYCALC_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    df = pd.json_normalize(data)

    column_map = {
        "player.name": "name",
        "player.position": "position",
        "player.maybeTeam": "team",
        "player.maybeYoe": "years_exp",
        "player.sleeperId": "sleeper_id",
        "player.mflId": "mfl_id",
        "player.maybeAge": "age",
        "value": "fc_value",
        "overallRank": "fc_rank",
        "positionRank": "fc_pos_rank",
        "maybeTier": "fc_tier",
        "trend30Day": "fc_trend_30d",
        "redraftValue": "fc_redraft_value",
    }

    df = df.rename(columns=column_map)
    keep_cols = list(column_map.values())
    df = df[[c for c in keep_cols if c in df.columns]]

    # Filter to skill positions + QB
    df = df[df["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    df["is_rookie"] = df["years_exp"] == 0
    df = df.reset_index(drop=True)
    return df
