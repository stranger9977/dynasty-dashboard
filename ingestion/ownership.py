import pandas as pd


def annotate_ownership(df: pd.DataFrame, ownership_map: dict[str, str]) -> pd.DataFrame:
    df = df.copy()

    def _get_owner(row):
        sid = row.get("sleeper_id")
        if pd.notna(sid) and str(sid) != "":
            owner = ownership_map.get(str(sid))
            if owner:
                return owner
        # Not on any roster — distinguish incoming rookies from free agents
        if row.get("is_rookie"):
            return "Incoming Rookie"
        if pd.isna(sid) or str(sid) == "":
            return "Unknown"
        return "Free Agent"

    df["owner"] = df.apply(_get_owner, axis=1)
    return df
